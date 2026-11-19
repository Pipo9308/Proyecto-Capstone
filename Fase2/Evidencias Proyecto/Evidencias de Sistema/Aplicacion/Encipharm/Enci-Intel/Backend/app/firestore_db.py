"""Capa de datos de Enci-Intel sobre Cloud Firestore, con la forma de la API de Mongo que ya usa el codigo.

Cubre solo lo que Intel usa: find / find_one (con sort, skip, limit, to_list), insert_one / insert_many,
update_one (con $set y upsert), bulk_write(UpdateOne), delete_one / delete_many y count_documents, con los
operadores $in, $lt, $lte, $gt, $gte, $ne, $regex ($options "i") y $or. Cualquier otra cosa lanza un error
claro en vez de devolver datos equivocados.

Decisiones para no depender de indices compuestos (Firestore los exige en produccion, el emulador no):
- A Firestore se le pide como maximo UNA condicion; el resto se evalua en Python sobre lo que vuelve.
- Con filtro + sort, el orden se hace en Python; solo "sort sin filtro" usa order_by del servidor.
shortcut: un filtro con varias condiciones, regex u $or lee la coleccion (o el resultado de la primera condicion)
completa; subir a indices compuestos / busqueda dedicada si alguna coleccion pasa de unos miles de documentos.
shortcut: order_by del servidor omite los documentos que no tienen el campo (Mongo los incluia).

Las fechas se devuelven como datetime ingenuos en UTC, como las entregaba Mongo.
"""
import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# Una variable vacia (docker-compose la deja asi para "sin emulador") el cliente la toma como un host invalido.
if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
    os.environ.pop("FIRESTORE_EMULATOR_HOST", None)

_RANGE_OPS = {"$lt": "<", "$lte": "<=", "$gt": ">", "$gte": ">=", "$ne": "!=", "$in": "in"}
_BATCH = 400


# ── Tipos con la forma de pymongo ────────────────────────────────────────────

@dataclass
class UpdateOne:
    filter: dict
    update: dict
    upsert: bool = False


@dataclass
class InsertOneResult:
    inserted_id: str


@dataclass
class DeleteResult:
    deleted_count: int


@dataclass
class UpdateResult:
    matched_count: int
    modified_count: int
    upserted_id: str | None = None


# ── Conversion de valores ────────────────────────────────────────────────────

def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _clean(value: Any) -> Any:
    """Fechas con zona -> ingenuas UTC, dentro de dicts y listas."""
    if isinstance(value, datetime):
        return _naive_utc(value)
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    return value


def _doc(snapshot) -> dict:
    data = _clean(snapshot.to_dict() or {})
    data["_id"] = snapshot.id
    return data


def _payload(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k != "_id"}


# ── Evaluacion de filtros en Python ──────────────────────────────────────────

def _cond(actual: Any, cond: Any) -> bool:
    if not isinstance(cond, dict) or not any(k.startswith("$") for k in cond):
        return actual == _clean(cond)
    for op, expected in cond.items():
        expected = _clean(expected)
        if op == "$in":
            ok = actual in expected
        elif op == "$ne":
            ok = actual != expected
        elif op == "$regex":
            flags = re.IGNORECASE if "i" in cond.get("$options", "") else 0
            ok = isinstance(actual, str) and re.search(expected, actual, flags) is not None
        elif op == "$options":
            continue
        elif op in ("$lt", "$lte", "$gt", "$gte"):
            if actual is None:
                return False
            ok = {"$lt": actual < expected, "$lte": actual <= expected, "$gt": actual > expected, "$gte": actual >= expected}[op]
        else:
            raise NotImplementedError(f"Operador de consulta no soportado: {op}")
        if not ok:
            return False
    return True


def _match(doc: dict, query: dict) -> bool:
    for key, cond in query.items():
        if key == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
        elif key.startswith("$"):
            raise NotImplementedError(f"Operador de consulta no soportado: {key}")
        elif not _cond(doc.get(key), cond):
            return False
    return True


def _sort_key(value: Any):
    return (value is not None, value if value is not None else 0)


def _sorted(docs: list[dict], sort: list[tuple[str, int]]) -> list[dict]:
    for field, direction in reversed(sort):  # estable: se ordena por el ultimo criterio primero
        docs = sorted(docs, key=lambda d: _sort_key(d.get(field)), reverse=direction < 0)
    return docs


def _server_condition(query: dict):
    """(campo, operador, valor) de la primera condicion que Firestore sabe resolver, o None."""
    for key, cond in query.items():
        if key.startswith("$") or key == "_id":
            continue
        if not isinstance(cond, dict):
            return key, "==", _clean(cond)
        ops = {k: v for k, v in cond.items() if k in _RANGE_OPS}
        if ops and len(ops) == len([k for k in cond if k != "$options"]):
            op, value = next(iter(ops.items()))
            if op == "$in" and not 0 < len(value) <= 30:
                continue
            return key, _RANGE_OPS[op], _clean(value)
    return None


def _check_update(update: dict) -> dict:
    extra = set(update) - {"$set"}
    if extra:
        raise NotImplementedError(f"Operador de actualizacion no soportado: {', '.join(sorted(extra))}")
    return _clean(update.get("$set", {}))


def _ruta(campo: str) -> str:
    """Nombre de campo listo para Firestore: los que tienen espacios o tildes ("Nombre comercial", columnas del SAG)
    van entre comillas invertidas; "a.b" sigue siendo un campo anidado."""
    from google.cloud.firestore_v1.field_path import FieldPath

    return FieldPath(*campo.split(".")).to_api_repr()


def _id_filter(query: dict):
    """Ids pedidos directamente por `_id` (igualdad o $in), o None."""
    cond = query.get("_id")
    if cond is None:
        return None
    if isinstance(cond, dict):
        return [str(i) for i in cond["$in"]] if set(cond) == {"$in"} else None
    return [str(cond)]


def _upsert_seed(query: dict) -> dict:
    """Campos de igualdad del filtro: un upsert los incluye en el documento nuevo (como Mongo)."""
    return {k: _clean(v) for k, v in query.items() if not k.startswith("$") and k != "_id" and not isinstance(v, dict)}


# ── Cursor ───────────────────────────────────────────────────────────────────

class _Cursor:
    def __init__(self, loader):
        self._loader = loader  # async (sort, skip, limit) -> list[dict]
        self._sort: list[tuple[str, int]] = []
        self._skip = 0
        self._limit: int | None = None

    def sort(self, key, direction=1):
        self._sort = [(key, direction)] if isinstance(key, str) else list(key)
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n or None
        return self

    async def to_list(self, length=None):
        docs = await self._loader(self._sort, self._skip, self._limit)
        return docs if length is None else docs[:length]

    def __aiter__(self):
        async def gen():
            for d in await self.to_list():
                yield d
        return gen()


# ── Coleccion asincrona ──────────────────────────────────────────────────────

class AsyncCollection:
    def __init__(self, client, name: str):
        self._client = client
        self._col = client.collection(name)

    async def _fetch(self, query: dict, sort, skip, limit) -> list[dict]:
        ids = _id_filter(query)
        if ids is not None:
            refs = [self._col.document(i) for i in ids]
            snaps = [s async for s in self._client.get_all(refs)] if refs else []
            docs = [_doc(s) for s in snaps if s.exists]
        else:
            cond = _server_condition(query)
            ref = self._col
            server_sort = bool(sort) and not query  # sort sin filtro: lo resuelve Firestore
            if cond:
                from google.cloud.firestore_v1.base_query import FieldFilter
                campo, operador, valor = cond
                ref = ref.where(filter=FieldFilter(_ruta(campo), operador, valor))
            if server_sort:
                from google.cloud.firestore_v1 import Query
                for field, direction in sort:
                    ref = ref.order_by(_ruta(field), direction=Query.DESCENDING if direction < 0 else Query.ASCENDING)
                if skip:
                    ref = ref.offset(skip)
                if limit:
                    ref = ref.limit(limit)
            docs = [_doc(s) async for s in ref.stream()]
            if server_sort:
                return docs
        docs = [d for d in docs if _match(d, query)]
        if sort:
            docs = _sorted(docs, sort)
        docs = docs[skip:]
        return docs[:limit] if limit else docs

    def find(self, query: dict | None = None, *_args, **_kw):
        query = query or {}
        return _Cursor(lambda sort, skip, limit: self._fetch(query, sort, skip, limit))

    async def find_one(self, query: dict | None = None, sort=None, **_kw):
        docs = await self.find(query or {}).sort(sort or []).limit(1).to_list()
        return docs[0] if docs else None

    async def count_documents(self, query: dict | None = None) -> int:
        return len(await self._fetch(query or {}, [], 0, None))

    async def insert_one(self, doc: dict) -> InsertOneResult:
        ref = self._col.document(str(doc["_id"])) if "_id" in doc else self._col.document()
        await ref.set(_payload(_clean(doc)))
        return InsertOneResult(ref.id)

    async def insert_many(self, docs: list[dict]) -> list[str]:
        ids = []
        for start in range(0, len(docs), _BATCH):
            batch = self._client.batch()
            for doc in docs[start:start + _BATCH]:
                ref = self._col.document(str(doc["_id"])) if "_id" in doc else self._col.document()
                batch.set(ref, _payload(_clean(doc)))
                ids.append(ref.id)
            await batch.commit()
        return ids

    async def update_one(self, query: dict, update: dict, upsert: bool = False) -> UpdateResult:
        fields = _check_update(update)
        existing = await self.find_one(query)
        if existing:
            if fields:
                await self._col.document(existing["_id"]).update(fields)
            return UpdateResult(1, 1 if fields else 0)
        if not upsert:
            return UpdateResult(0, 0)
        ref = self._col.document(str(query["_id"])) if "_id" in query else self._col.document()
        await ref.set({**_upsert_seed(query), **fields}, merge=True)
        return UpdateResult(0, 0, ref.id)

    async def bulk_write(self, ops: list[UpdateOne]) -> None:
        # Todas las operaciones de Intel son upserts por _id: se escriben por lotes con merge.
        for start in range(0, len(ops), _BATCH):
            batch = self._client.batch()
            for op in ops[start:start + _BATCH]:
                if "_id" not in op.filter or not op.upsert:
                    raise NotImplementedError("bulk_write solo soporta UpdateOne(upsert=True) por _id")
                batch.set(self._col.document(str(op.filter["_id"])), _check_update(op.update), merge=True)
            await batch.commit()

    async def _delete(self, query: dict, limit: int | None) -> DeleteResult:
        docs = await self._fetch(query, [], 0, limit)
        for start in range(0, len(docs), _BATCH):
            batch = self._client.batch()
            for d in docs[start:start + _BATCH]:
                batch.delete(self._col.document(d["_id"]))
            await batch.commit()
        return DeleteResult(len(docs))

    async def delete_one(self, query: dict) -> DeleteResult:
        return await self._delete(query, 1)

    async def delete_many(self, query: dict | None = None) -> DeleteResult:
        return await self._delete(query or {}, None)


class AsyncDatabase:
    def __init__(self, client):
        self.client = client
        self._cols: dict[str, AsyncCollection] = {}

    def __getitem__(self, name: str) -> AsyncCollection:
        if name not in self._cols:
            self._cols[name] = AsyncCollection(self.client, name)
        return self._cols[name]

    def __getattr__(self, name: str) -> AsyncCollection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]


def clean_project_id(value: str | None) -> str | None:
    """Un id de proyecto de GCP nunca lleva espacios ni punto final: un descuido al copiarlo daba 403 CONSUMER_INVALID."""
    return value.strip().rstrip(".") if value else value


def credentials_from_env():
    """Credenciales de la cuenta de servicio desde FIREBASE_CREDENTIALS_JSON (el JSON completo en una variable).

    Es lo mas simple en hostings como Render: no depende de montar un archivo. Sin la variable devuelve None y el
    cliente usa GOOGLE_APPLICATION_CREDENTIALS / FIREBASE_CREDENTIALS_PATH, o el emulador."""
    raw = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
    if not raw:
        return None
    import json

    from google.oauth2 import service_account
    try:
        return service_account.Credentials.from_service_account_info(json.loads(raw))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RuntimeError(f"FIREBASE_CREDENTIALS_JSON no es un JSON de cuenta de servicio valido: {error}") from error


def create_async_database(project_id: str | None = None) -> AsyncDatabase:
    """Cliente asincrono de Firestore. Con FIRESTORE_EMULATOR_HOST apunta al emulador local."""
    from google.cloud.firestore_v1.async_client import AsyncClient
    return AsyncDatabase(AsyncClient(project=clean_project_id(project_id), credentials=credentials_from_env()))


# ── Version sincrona (los agentes de scraping corren como procesos aparte) ───

class _Sync:
    """Ejecuta la coleccion asincrona en un bucle propio: misma logica, sin duplicarla."""

    def __init__(self, collection: AsyncCollection, loop: asyncio.AbstractEventLoop):
        self._c, self._loop = collection, loop

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def find(self, query=None, *a, **kw):
        cursor = self._c.find(query, *a, **kw)
        run = self._run

        class SyncCursor(_Cursor):
            def to_list(self, length=None):
                return run(super().to_list(length))

            def __iter__(self):
                return iter(self.to_list())

        sync = SyncCursor(cursor._loader)
        return sync

    def find_one(self, query=None, **kw):
        return self._run(self._c.find_one(query, **kw))

    def __getattr__(self, name):
        method = getattr(self._c, name)
        return lambda *a, **kw: self._run(method(*a, **kw))


class SyncDatabase:
    def __init__(self, project_id: str | None = None):
        # shortcut: el AsyncClient queda atado a este bucle; los agentes lo usan solo desde este hilo.
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._db = create_async_database(project_id)
        self._cols: dict[str, _Sync] = {}

    def __getitem__(self, name):
        if name not in self._cols:
            self._cols[name] = _Sync(self._db[name], self._loop)
        return self._cols[name]

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]
