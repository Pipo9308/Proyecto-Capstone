"""Capa de datos de Ventas sobre Cloud Firestore, con la forma de SQLAlchemy que el codigo ya usaba.

Los modelos se declaran igual (Column, String, ForeignKey...), y se consulta igual: `db.query(Modelo).filter(...)
.order_by(...).limit(n).all()`, `db.add(obj)`, `db.commit()`. Cada modelo es una coleccion; el id del documento es la
clave primaria. Solo se implementa lo que Ventas usa; lo demas lanza NotImplementedError en vez de dar datos falsos.

Diferencias respecto de una base relacional (a conocer):
- Un commit escribe todo en un lote atomico de Firestore (hasta 500 operaciones); no hay transacciones de lectura-escritura.
- Unicidad (`Unique`, `unique=True`): se garantiza con un documento guardia `_unique/<hash>` creado en el mismo lote;
  si ya existe, el commit falla con IntegrityError. Es atomico incluso con peticiones concurrentes.
- Sin claves foraneas ni cascadas: quien borra un registro borra sus hijos (los servicios ya lo hacen).
- Los filtros se evaluan asi: Firestore resuelve la busqueda por id y UNA condicion simple; el resto, ordenar y paginar
  se hace en Python sobre lo que vuelve (no hay indices compuestos que mantener).
  shortcut: una consulta sin filtro por id lee la coleccion completa (o el resultado de la primera condicion); pasar a
  indices compuestos / paginacion por cursor si una coleccion supera unos miles de documentos.
- Las fechas se guardan y devuelven como datetime ingenuos en UTC; las `Date` se guardan como texto ISO.
"""
import hashlib
import os
import re
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable

_UNSET = object()
# Intel y Ventas comparten el proyecto de Firestore: las colecciones de Ventas llevan prefijo para no chocar con las de
# Intel (ambos tienen "users", con campos distintos).
COLLECTION_PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "ventas_")
_UNIQUE = f"{COLLECTION_PREFIX}_unique"


class IntegrityError(Exception):
    """Violacion de unicidad o de columna obligatoria (como la de SQLAlchemy)."""


class NoResultFound(Exception):
    pass


class MultipleResultsFound(Exception):
    pass


# ── Tipos de columna (solo para saber como guardar el valor) ─────────────────

class _Type:
    kind = "str"

    def __init__(self, *args, **kwargs):
        self.args = args


class String(_Type):
    kind = "str"


class Text(String):
    pass


class Integer(_Type):
    kind = "int"


class Float(_Type):
    kind = "float"


class Numeric(Float):
    pass


class Boolean(_Type):
    kind = "bool"


class DateTime(_Type):
    kind = "datetime"


class Date(_Type):
    kind = "date"


class JSON(_Type):
    kind = "json"


class Vector(_Type):
    kind = "vector"


class ForeignKey:
    """Solo documenta la relacion: Firestore no valida claves foraneas."""

    def __init__(self, target, **kwargs):
        self.target = target


# ── Expresiones ──────────────────────────────────────────────────────────────

def _norm(value):
    """Valores que se comparan/guardan: fechas con zona -> ingenuas UTC, Decimal -> float."""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, Decimal):
        return float(value)
    return value


def _wire(value):
    """Valor tal como se guarda en Firestore (las fechas `date` van como texto ISO, que ordena igual)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    return _norm(value)


def _like_regex(pattern: str, escape: str | None) -> re.Pattern:
    out, i = [], 0
    while i < len(pattern):
        ch = pattern[i]
        if escape and ch == escape and i + 1 < len(pattern):
            out.append(re.escape(pattern[i + 1]))
            i += 2
            continue
        out.append(".*" if ch == "%" else "." if ch == "_" else re.escape(ch))
        i += 1
    return re.compile("^" + "".join(out) + "$", re.DOTALL)


class Cond:
    """Una condicion `campo <op> valor`, con la semantica NULL de SQL (comparar contra NULL no coincide)."""

    def __init__(self, name: str, op: str, value: Any, extra: Any = None):
        self.name, self.op, self.value, self.extra = name, op, value, extra
        self._regex = _like_regex(value, extra) if op in ("like", "ilike") else None

    def test(self, data: dict) -> bool:
        actual = data.get(self.name)
        op, expected = self.op, self.value
        if op == "is":
            return actual is expected if expected is None else actual == expected
        if op == "isnot":
            return actual is not None if expected is None else actual != expected
        if actual is None:
            return False
        actual = _norm(actual)
        if op == "==":
            return actual == expected
        if op == "!=":
            return actual != expected
        if op == "ieq":
            return isinstance(actual, str) and actual.lower() == expected
        if op == "in":
            return actual in expected
        if op in ("like", "ilike"):
            if not isinstance(actual, str):
                return False
            return self._regex.match(actual if op == "like" else actual.lower()) is not None if op == "like" else \
                re.match(self._regex.pattern, actual, re.DOTALL | re.IGNORECASE) is not None
        try:
            return {"<": actual < expected, "<=": actual <= expected, ">": actual > expected, ">=": actual >= expected}[op]
        except TypeError:
            return False

    def pushdown(self):
        """(campo, operador, valor) si Firestore lo resuelve solo."""
        if self.op in ("==", "<", "<=", ">", ">=") and self.value is not None:
            return self.name, self.op, _wire(self.value)
        if self.op == "in" and 0 < len(self.value) <= 30:
            return self.name, "in", [_wire(v) for v in self.value]
        return None


class BoolCond:
    def __init__(self, kind: str, conds):
        self.kind, self.conds = kind, conds

    def test(self, data: dict) -> bool:
        results = (c.test(data) for c in self.conds)
        return any(results) if self.kind == "or" else all(results)

    def pushdown(self):
        return None


def or_(*conds):
    return BoolCond("or", conds)


def and_(*conds):
    return BoolCond("and", conds)


class _Lower:
    """func.lower(Modelo.campo) == "texto"."""

    def __init__(self, field: "Field"):
        self.field = field

    def __eq__(self, other):
        return Cond(self.field.name, "ieq", str(other).lower())


class _Func:
    @staticmethod
    def lower(field):
        return _Lower(field)


func = _Func()


class Order:
    def __init__(self, field: "Field", desc: bool):
        self.field, self.desc = field, desc


# ── Campos ───────────────────────────────────────────────────────────────────

class Field:
    def __init__(self, type_=None, *args, primary_key=False, nullable=True, default=_UNSET, onupdate=None, unique=False,
                 index=False, server_default=None, **kwargs):
        self.kind = getattr(type_, "kind", "str")  # sirve para Date y para Date()
        self.primary = primary_key
        self.nullable = nullable and not primary_key
        self.default = default
        self.on_update = onupdate
        self.unique = unique
        self.name = None
        self.owner = None

    def __set_name__(self, owner, name):
        self.name, self.owner = name, owner

    def default_value(self):
        if self.default is _UNSET:
            return None
        return _norm(self.default() if callable(self.default) else self.default)

    # acceso: Modelo.campo -> expresion; instancia.campo -> valor
    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        return obj._data.get(self.name)

    def __set__(self, obj, value):
        obj._data[self.name] = _norm(value)
        obj._dirty.add(self.name)

    __hash__ = object.__hash__

    def __eq__(self, other):
        return Cond(self.name, "==", _norm(other)) if other is not None else Cond(self.name, "is", None)

    def __ne__(self, other):
        return Cond(self.name, "!=", _norm(other)) if other is not None else Cond(self.name, "isnot", None)

    def __lt__(self, other):
        return Cond(self.name, "<", _norm(other))

    def __le__(self, other):
        return Cond(self.name, "<=", _norm(other))

    def __gt__(self, other):
        return Cond(self.name, ">", _norm(other))

    def __ge__(self, other):
        return Cond(self.name, ">=", _norm(other))

    def in_(self, values):
        return Cond(self.name, "in", [_norm(v) for v in values])

    def is_(self, value):
        return Cond(self.name, "is", value)

    def isnot(self, value):
        return Cond(self.name, "isnot", value)

    def like(self, pattern, escape=None):
        return Cond(self.name, "like", pattern, escape)

    def ilike(self, pattern, escape=None):
        return Cond(self.name, "ilike", pattern, escape)

    def desc(self):
        return Order(self, True)

    def asc(self):
        return Order(self, False)


def Column(*args, **kwargs) -> Field:
    type_ = next((a for a in args if isinstance(a, _Type) or (isinstance(a, type) and issubclass(a, _Type))), None)
    return Field(type_, **{k: v for k, v in kwargs.items()})


class Unique:
    """Restriccion de unicidad sobre uno o mas campos; `where` la limita a los registros que cumplen (parcial)."""

    def __init__(self, *fields: str, where: Callable[[dict], bool] | None = None):
        self.fields, self.where = fields, where


# ── Documentos ───────────────────────────────────────────────────────────────

class Document:
    __tablename__: str = ""
    __fields__: dict[str, Field] = {}
    __unique__: tuple[Unique, ...] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        fields = {}
        for base in reversed(cls.__mro__):
            for name, value in vars(base).items():
                if isinstance(value, Field):
                    fields[name] = value
        cls.__fields__ = fields
        cls.__pk__ = next((n for n, f in fields.items() if f.primary), None)
        uniques = list(getattr(cls, "__unique__", ()))
        uniques += [Unique(n) for n, f in fields.items() if f.unique]
        cls.__unique_all__ = tuple(uniques)

    def __init__(self, **kwargs):
        object.__setattr__(self, "_data", {})
        object.__setattr__(self, "_dirty", set())
        object.__setattr__(self, "_orig", None)
        for name, field in self.__fields__.items():
            self._data[name] = field.default_value()
        for key, value in kwargs.items():
            if key not in self.__fields__:
                raise TypeError(f"{type(self).__name__} no tiene el campo {key!r}")
            setattr(self, key, value)
        self._dirty = set(self._data)

    @property
    def __dict__(self):  # algunos servicios leen user_obj.__dict__ (como el de SQLAlchemy)
        return dict(self._data)

    @classmethod
    def _from_snapshot(cls, snap):
        obj = cls.__new__(cls)
        object.__setattr__(obj, "_data", {})
        object.__setattr__(obj, "_dirty", set())
        data = snap.to_dict() or {}
        for name, field in cls.__fields__.items():
            value = data.get(name, _UNSET)
            obj._data[name] = field.default_value() if value is _UNSET else _load(field, value)
        if cls.__pk__:
            obj._data[cls.__pk__] = snap.id
        object.__setattr__(obj, "_orig", dict(obj._data))
        return obj

    @classmethod
    def collection_name(cls) -> str:
        return COLLECTION_PREFIX + cls.__tablename__

    def _pk_value(self):
        return self._data.get(self.__pk__) if self.__pk__ else None


def _load(field: Field, value):
    if value is None:
        return None
    if field.kind == "datetime" and isinstance(value, datetime):
        return _norm(value)
    if field.kind == "date" and isinstance(value, str):
        return date.fromisoformat(value)
    if field.kind == "vector":
        return list(value)
    return value


def _dump(field: Field, value):
    value = _norm(value)
    if value is None:
        return None
    if field.kind == "date" and isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if field.kind == "vector":
        from google.cloud.firestore_v1.vector import Vector as FsVector
        return FsVector(list(value))
    return value


class Row:
    """Fila de `query(Modelo.a, Modelo.b)`: se lee por indice o por nombre."""

    def __init__(self, names, values):
        self._names, self._values = names, values

    def __getitem__(self, index):
        return self._values[index]

    def __getattr__(self, name):
        try:
            return self._values[self._names.index(name)]
        except ValueError:
            raise AttributeError(name) from None

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)


# ── Consulta ─────────────────────────────────────────────────────────────────

class Query:
    def __init__(self, session: "Session", entities):
        self.session = session
        self.entities = entities
        first = entities[0]
        self.model = first if isinstance(first, type) else first.owner
        self._conds: list = []
        self._order: list[Order] = []
        self._limit: int | None = None
        self._offset = 0

    def filter(self, *conds):
        self._conds.extend(conds)
        return self

    def filter_by(self, **kwargs):
        self._conds.extend(Cond(k, "==", _norm(v)) for k, v in kwargs.items())
        return self

    def order_by(self, *keys):
        self._order.extend(k if isinstance(k, Order) else Order(k, False) for k in keys)
        return self

    def limit(self, n):
        self._limit = n
        return self

    def offset(self, n):
        self._offset = n or 0
        return self

    def with_for_update(self):
        return self  # sin bloqueos de fila: ver la nota de concurrencia en cada servicio que lo use

    def join(self, *args, **kwargs):
        raise NotImplementedError("join no esta soportado: se resuelve en el servicio")

    # -- ejecucion --
    def _matches(self) -> list[Document]:
        model, coll = self.model, self.session.client.collection(self.model.collection_name())
        pk = model.__pk__
        docs: list[Document] | None = None
        rest = list(self._conds)
        for cond in rest:
            if isinstance(cond, Cond) and cond.name == pk and cond.op in ("==", "in"):
                ids = [cond.value] if cond.op == "==" else list(cond.value)
                docs = [d for d in (self.session._get(model, str(i)) for i in ids if i is not None) if d is not None]
                break
        if docs is None:
            ref, _ = self._server_query(coll)
            docs = [self.session._hydrate(model, snap) for snap in ref.stream()]
        docs = [d for d in docs if all(c.test(d._data) for c in rest)]
        for key in reversed(self._order):
            docs = sorted(docs, key=lambda d, k=key: _sort_key(d._data.get(k.field.name)), reverse=key.desc)
        docs = docs[self._offset:]
        return docs[: self._limit] if self._limit is not None else docs

    def _server_query(self, coll):
        """Firestore resuelve TODAS las igualdades (no piden indice compuesto) o, sin igualdades, una condicion de rango.
        Devuelve (consulta, condiciones que Firestore no resolvio y hay que revisar en Python)."""
        from google.cloud.firestore_v1.base_query import FieldFilter

        ref, residual, ranged = coll, [], False
        specs = [(c, c.pushdown()) for c in self._conds]
        has_equality = any(spec and spec[1] in ("==", "in") for _, spec in specs)
        for cond, spec in specs:
            usable = spec is not None and (spec[1] in ("==", "in") or (not has_equality and not ranged))
            if usable and spec[1] not in ("==", "in"):
                ranged = True
            if usable:
                ref = ref.where(filter=FieldFilter(*spec))
            else:
                residual.append(cond)
        return ref, residual

    def _shape(self, doc: Document):
        if isinstance(self.entities[0], type):
            return doc
        values = tuple(doc._data.get(e.name) for e in self.entities)
        return Row([e.name for e in self.entities], values)

    def all(self):
        return [self._shape(d) for d in self._matches()]

    def __iter__(self):
        return iter(self.all())

    def first(self):
        rows = self._matches()
        return self._shape(rows[0]) if rows else None

    def one(self):
        rows = self._matches()
        if not rows:
            raise NoResultFound()
        if len(rows) > 1:
            raise MultipleResultsFound()
        return self._shape(rows[0])

    def one_or_none(self):
        rows = self._matches()
        if len(rows) > 1:
            raise MultipleResultsFound()
        return self._shape(rows[0]) if rows else None

    def count(self):
        if not self._order and self._limit is None and not self._offset and not any(
            isinstance(c, Cond) and c.name == self.model.__pk__ and c.op in ("==", "in") for c in self._conds
        ):
            ref, residual = self._server_query(self.session.client.collection(self.model.collection_name()))
            if not residual:  # Firestore lo cuenta sin traer los documentos
                return ref.count().get()[0][0].value
        return len(self._matches())

    def delete(self, synchronize_session=None):
        docs = self._matches()
        self.session._delete_now(docs)
        return len(docs)

    def update(self, values: dict, synchronize_session=None):
        docs = self._matches()
        for doc in docs:
            for key, value in values.items():
                name = key.name if isinstance(key, Field) else key
                setattr(doc, name, value)
        self.session.flush()
        return len(docs)


def _sort_key(value):
    # NULL es el valor menor (como en SQLite, con el que se probaron los servicios).
    return (value is not None, value if value is not None else 0)


# ── Sesion ───────────────────────────────────────────────────────────────────

_BATCH_LIMIT = 450


class Session:
    def __init__(self, client):
        self.client = client
        self._identity: dict[tuple[str, str], Document] = {}
        self._new: list[Document] = []
        self._deleted: list[Document] = []

    # contexto
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        self._identity.clear()
        self._new.clear()
        self._deleted.clear()

    # consulta
    def query(self, *entities):
        if not entities:
            raise TypeError("query() necesita un modelo o campos")
        return Query(self, entities)

    def nearest(self, model, field: str, vector, limit: int) -> list[tuple[Document, float]]:
        """Los `limit` documentos mas cercanos al vector (distancia coseno, menor = mas parecido).

        Usa Firestore Vector Search: la coleccion necesita un indice vectorial del campo (ver scripts/create_vector_index.py).
        El emulador de Firestore no soporta busqueda vectorial: se prueba contra un proyecto real."""
        from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
        from google.cloud.firestore_v1.vector import Vector as FsVector

        query = self.client.collection(model.collection_name()).find_nearest(
            vector_field=field, query_vector=FsVector([float(x) for x in vector]),
            distance_measure=DistanceMeasure.COSINE, limit=limit, distance_result_field="_distance",
        )
        return [(self._hydrate(model, snap), snap.to_dict()["_distance"]) for snap in query.stream()]

    def get(self, model, pk):
        return self._get(model, str(pk))

    def _get(self, model, pk: str):
        cached = self._identity.get((model.__tablename__, pk))
        if cached is not None:
            return cached
        snap = self.client.collection(model.collection_name()).document(pk).get()
        return self._hydrate(model, snap) if snap.exists else None

    def _hydrate(self, model, snap):
        key = (model.__tablename__, snap.id)
        cached = self._identity.get(key)
        if cached is not None:
            return cached
        obj = model._from_snapshot(snap)
        self._identity[key] = obj
        return obj

    # escritura
    def add(self, obj: Document):
        if obj not in self._new and obj._orig is None:
            self._new.append(obj)

    def add_all(self, objs):
        for obj in objs:
            self.add(obj)

    def delete(self, obj: Document):
        if obj in self._new:
            self._new.remove(obj)
        else:
            self._deleted.append(obj)

    def refresh(self, obj: Document):
        snap = self.client.collection(obj.collection_name()).document(str(obj._pk_value())).get()
        if snap.exists:
            fresh = type(obj)._from_snapshot(snap)
            obj._data.update(fresh._data)
            object.__setattr__(obj, "_orig", dict(fresh._data))
            obj._dirty.clear()

    def expire_all(self):
        self._identity.clear()

    def rollback(self):
        for obj in self._new:
            self._identity.pop((obj.__tablename__, str(obj._pk_value())), None)
        self._new.clear()
        self._deleted.clear()
        for obj in list(self._identity.values()):
            if obj._dirty and obj._orig is not None:
                obj._data.update(obj._orig)
                obj._dirty.clear()

    def commit(self):
        self.flush()

    def flush(self):
        from google.api_core.exceptions import AlreadyExists, FailedPrecondition

        ops: list[Callable] = []
        batch = self.client.batch()

        def stage(fn):
            fn(batch)
            ops.append(fn)

        pending = []
        for obj in self._new:
            pk = obj.__pk__
            if pk and not obj._data.get(pk):
                obj._data[pk] = str(uuid.uuid4())
            for name, field in obj.__fields__.items():
                if not field.nullable and obj._data.get(name) is None:
                    raise IntegrityError(f"{obj.__tablename__}.{name} no puede ser nulo")
            ref = self.client.collection(obj.collection_name()).document(str(obj._pk_value()))
            stage(lambda b, r=ref, o=obj: b.create(r, _serialize(o, o._data.keys())))
            for guard in self._guards(obj, obj._data):
                stage(lambda b, g=guard: b.create(self.client.collection(_UNIQUE).document(g), {"t": 1}))
            pending.append(("new", obj))
        for obj in list(self._identity.values()):
            if obj._orig is None or not obj._dirty:
                continue
            for name, field in obj.__fields__.items():
                if field.on_update and name not in obj._dirty:
                    obj._data[name] = _norm(field.on_update())
                    obj._dirty.add(name)
                if not field.nullable and obj._data.get(name) is None:
                    raise IntegrityError(f"{obj.__tablename__}.{name} no puede ser nulo")
            ref = self.client.collection(obj.collection_name()).document(str(obj._pk_value()))
            stage(lambda b, r=ref, o=obj: b.update(r, _serialize(o, o._dirty)))
            old, new = set(self._guards(obj, obj._orig)), set(self._guards(obj, obj._data))
            for guard in old - new:
                stage(lambda b, g=guard: b.delete(self.client.collection(_UNIQUE).document(g)))
            for guard in new - old:
                stage(lambda b, g=guard: b.create(self.client.collection(_UNIQUE).document(g), {"t": 1}))
            pending.append(("dirty", obj))
        for obj in self._deleted:
            ref = self.client.collection(obj.collection_name()).document(str(obj._pk_value()))
            stage(lambda b, r=ref: b.delete(r))
            for guard in self._guards(obj, obj._orig or obj._data):
                stage(lambda b, g=guard: b.delete(self.client.collection(_UNIQUE).document(g)))
            pending.append(("deleted", obj))

        if not ops:
            return
        if len(ops) > _BATCH_LIMIT:  # shortcut: por encima de 500 operaciones se pierde la atomicidad
            for start in range(0, len(ops), _BATCH_LIMIT):
                part = self.client.batch()
                for fn in ops[start:start + _BATCH_LIMIT]:
                    fn(part)
                self._commit(part, AlreadyExists, FailedPrecondition)
        else:
            self._commit(batch, AlreadyExists, FailedPrecondition)
        for kind, obj in pending:
            key = (obj.__tablename__, str(obj._pk_value()))
            if kind == "deleted":
                self._identity.pop(key, None)
            else:
                self._identity[key] = obj
                object.__setattr__(obj, "_orig", dict(obj._data))
                obj._dirty.clear()
        self._new.clear()
        self._deleted.clear()

    def _commit(self, batch, *duplicate_errors):
        try:
            batch.commit()
        except duplicate_errors as error:
            self._new.clear()
            raise IntegrityError(f"registro duplicado: {error}") from error

    @staticmethod
    def _guards(obj: Document, data: dict) -> list[str]:
        guards = []
        for spec in obj.__unique_all__:
            if spec.where and not spec.where(data):
                continue
            values = [data.get(f) for f in spec.fields]
            if any(v is None for v in values):
                continue  # NULL no choca con NULL, como en SQL
            raw = f"{obj.__tablename__}|{','.join(spec.fields)}|{[_norm(v) for v in values]!r}"
            guards.append(hashlib.sha1(raw.encode("utf-8")).hexdigest())
        return guards

    def _delete_now(self, docs: list[Document]):
        self._deleted.extend(docs)
        self.flush()


def _serialize(obj: Document, names) -> dict:
    return {n: _dump(obj.__fields__[n], obj._data.get(n)) for n in names if n in obj.__fields__ and n != obj.__pk__}


# ── Cliente de Firestore ─────────────────────────────────────────────────────

_client = None


def credentials_from_env():
    """Credenciales de la cuenta de servicio desde FIREBASE_CREDENTIALS_JSON (el JSON completo en una variable)."""
    raw = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
    if not raw:
        return None
    import json

    from google.oauth2 import service_account
    try:
        return service_account.Credentials.from_service_account_info(json.loads(raw))
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise RuntimeError(f"FIREBASE_CREDENTIALS_JSON no es un JSON de cuenta de servicio valido: {error}") from error


def clean_project_id(value: str | None) -> str | None:
    return value.strip().rstrip(".") if value else value


def get_client():
    """Cliente de Firestore compartido. Con FIRESTORE_EMULATOR_HOST apunta al emulador (variable vacia = sin emulador)."""
    global _client
    if _client is None:
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            os.environ.pop("FIRESTORE_EMULATOR_HOST", None)
        if os.environ.get("FIREBASE_CREDENTIALS_PATH"):
            os.environ.setdefault("GOOGLE_APPLICATION_CREDENTIALS", os.environ["FIREBASE_CREDENTIALS_PATH"])
        from google.cloud import firestore
        _client = firestore.Client(
            project=clean_project_id(os.environ.get("FIREBASE_PROJECT_ID")), credentials=credentials_from_env()
        )
    return _client


def new_session() -> Session:
    return Session(get_client())
