"""Capa Firestore con forma de Mongo. Corre contra el emulador de Firestore (FIRESTORE_EMULATOR_HOST);
sin emulador se omite. Levantarlo: docker run -p 8085:8085 gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators
gcloud emulators firestore start --host-port=0.0.0.0:8085"""
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

needs_emulator = pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="sin emulador de Firestore")

from app.firestore_db import SyncDatabase, UpdateOne, create_async_database  # noqa: E402


@pytest.fixture
def col():
    db = create_async_database("enci-test")
    return db[f"t_{uuid.uuid4().hex[:10]}"]


async def seed(col):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    await col.insert_many([
        {"_id": "a", "name": "Zoetis Chile", "n": 3, "created_at": now, "tag": "x"},
        {"_id": "b", "name": "Agrovet", "n": 1, "created_at": now + timedelta(days=1), "tag": "y"},
        {"_id": "c", "name": "Drag Pharma", "n": 2, "created_at": now + timedelta(days=2), "tag": "x"},
    ])


@needs_emulator
@pytest.mark.anyio
async def test_find_one_por_id_y_por_campo(col):
    await seed(col)

    assert (await col.find_one({"_id": "b"}))["name"] == "Agrovet"
    assert (await col.find_one({"name": "Drag Pharma"}))["_id"] == "c"
    assert await col.find_one({"_id": "zzz"}) is None
    assert await col.find_one({"name": "no existe"}) is None


@needs_emulator
@pytest.mark.anyio
async def test_las_fechas_vuelven_ingenuas_en_utc_como_en_mongo(col):
    await seed(col)

    doc = await col.find_one({"_id": "a"})

    assert doc["created_at"] == datetime(2026, 10, 1) and doc["created_at"].tzinfo is None


@needs_emulator
@pytest.mark.anyio
async def test_sort_skip_limit_con_y_sin_filtro(col):
    await seed(col)

    assert [d["_id"] for d in await col.find().sort("n", -1).to_list()] == ["a", "c", "b"]
    assert [d["_id"] for d in await col.find().sort("created_at", -1).limit(2).to_list()] == ["c", "b"]
    assert [d["_id"] for d in await col.find({"tag": "x"}).sort("n", 1).to_list()] == ["c", "a"]
    assert [d["_id"] for d in await col.find().sort("n", 1).skip(1).limit(1).to_list()] == ["c"]


@needs_emulator
@pytest.mark.anyio
async def test_operadores_in_lt_y_varias_condiciones(col):
    await seed(col)

    assert {d["_id"] for d in await col.find({"_id": {"$in": ["a", "c", "zzz"]}}).to_list()} == {"a", "c"}
    assert {d["_id"] for d in await col.find({"n": {"$lt": 3}}).to_list()} == {"b", "c"}
    assert {d["_id"] for d in await col.find({"tag": "x", "n": {"$gte": 3}}).to_list()} == {"a"}
    cutoff = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)  # un filtro con fecha con zona contra datos ingenuos
    assert {d["_id"] for d in await col.find({"created_at": {"$lt": cutoff}}).to_list()} == {"a", "b"}


@needs_emulator
@pytest.mark.anyio
async def test_regex_insensible_y_or(col):
    await seed(col)
    pattern = {"$regex": "ZOET|agro", "$options": "i"}

    assert {d["_id"] for d in await col.find({"name": pattern}).to_list()} == {"a", "b"}
    assert {d["_id"] for d in await col.find({"$or": [{"name": pattern}, {"_id": "c"}]}).to_list()} == {"a", "b", "c"}


@needs_emulator
@pytest.mark.anyio
async def test_operador_no_soportado_falla_en_voz_alta(col):
    await seed(col)

    with pytest.raises(NotImplementedError):
        await col.find({"n": {"$mod": [2, 0]}}).to_list()
    with pytest.raises(NotImplementedError):
        await col.update_one({"_id": "a"}, {"$inc": {"n": 1}})


@needs_emulator
@pytest.mark.anyio
async def test_insert_one_genera_id_y_count(col):
    result = await col.insert_one({"name": "nuevo"})

    assert isinstance(result.inserted_id, str) and len(result.inserted_id) >= 10
    assert (await col.find_one({"_id": result.inserted_id}))["name"] == "nuevo"
    assert await col.count_documents({}) == 1
    assert await col.count_documents({"name": "otro"}) == 0


@needs_emulator
@pytest.mark.anyio
async def test_update_one_set_por_campo_y_upsert(col):
    await seed(col)

    await col.update_one({"name": "Agrovet"}, {"$set": {"n": 10}})
    miss = await col.update_one({"_id": "zzz"}, {"$set": {"n": 1}})
    up = await col.update_one({"_id": "nuevo"}, {"$set": {"n": 7}}, upsert=True)
    by_field = await col.update_one({"email": "a@b.cl"}, {"$set": {"rol": "admin"}}, upsert=True)

    assert (await col.find_one({"_id": "b"}))["n"] == 10 and (await col.find_one({"_id": "b"}))["name"] == "Agrovet"
    assert miss.matched_count == 0 and await col.find_one({"_id": "zzz"}) is None
    assert up.upserted_id == "nuevo" and (await col.find_one({"_id": "nuevo"}))["n"] == 7
    created = await col.find_one({"_id": by_field.upserted_id})
    assert created["email"] == "a@b.cl" and created["rol"] == "admin"  # el upsert conserva los campos del filtro


@needs_emulator
@pytest.mark.anyio
async def test_bulk_write_upsert_mezcla_con_lo_existente(col):
    await seed(col)

    await col.bulk_write([UpdateOne({"_id": "a"}, {"$set": {"n": 99}}, upsert=True), UpdateOne({"_id": "z"}, {"$set": {"n": 5}}, upsert=True)])

    assert (await col.find_one({"_id": "a"}))["n"] == 99 and (await col.find_one({"_id": "a"}))["name"] == "Zoetis Chile"
    assert (await col.find_one({"_id": "z"}))["n"] == 5


@needs_emulator
@pytest.mark.anyio
async def test_delete_one_y_delete_many(col):
    await seed(col)

    assert (await col.delete_one({"tag": "x"})).deleted_count == 1
    assert (await col.delete_many({"n": {"$lt": 100}})).deleted_count == 2
    assert await col.count_documents({}) == 0


@needs_emulator
@pytest.mark.anyio
async def test_lotes_grandes(col):
    await col.insert_many([{"_id": f"d{i:04d}", "i": i} for i in range(950)])

    assert await col.count_documents({}) == 950
    assert (await col.delete_many({"i": {"$gte": 0}})).deleted_count == 950


@needs_emulator
def test_version_sincrona_para_los_agentes():
    db = SyncDatabase("enci-test")
    name = f"t_{uuid.uuid4().hex[:10]}"
    c = db[name]

    c.insert_many([{"_id": "a", "n": 1}, {"_id": "b", "n": 2}])
    c.bulk_write([UpdateOne({"_id": "a"}, {"$set": {"n": 5}}, upsert=True)])

    assert c.find_one({"_id": "a"})["n"] == 5
    assert [d["_id"] for d in c.find({}).sort("n", -1)] == ["a", "b"]
    assert c.delete_many({"n": {"$lt": 100}}).deleted_count == 2


# ── Credenciales desde variable de entorno (no necesitan emulador) ───────────

def test_credenciales_sin_variable_devuelve_none(monkeypatch):
    from app.firestore_db import credentials_from_env
    monkeypatch.delenv("FIREBASE_CREDENTIALS_JSON", raising=False)

    assert credentials_from_env() is None


@pytest.mark.parametrize("raw", ["no es json", '{"type": "service_account"}', "[]"])
def test_credenciales_invalidas_dan_un_error_claro(monkeypatch, raw):
    from app.firestore_db import credentials_from_env
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", raw)

    with pytest.raises(RuntimeError, match="FIREBASE_CREDENTIALS_JSON"):
        credentials_from_env()


@pytest.mark.parametrize("raw,expected", [("encipharm-12321.", "encipharm-12321"), (" encipharm-12321 \n", "encipharm-12321"), ("encipharm-12321", "encipharm-12321"), (None, None)])
def test_el_id_del_proyecto_se_limpia(raw, expected):
    from app.firestore_db import clean_project_id

    assert clean_project_id(raw) == expected


def test_los_nombres_con_espacios_se_citan_para_firestore():
    from app.firestore_db import _ruta

    assert _ruta("Nombre comercial") == "`Nombre comercial`"
    assert _ruta("status") == "status" and _ruta("data.x") == "data.x"


@needs_emulator
@pytest.mark.anyio
async def test_ordenar_y_filtrar_por_un_campo_con_espacios(col):
    """Columnas del SAG ("Nombre comercial"): antes Firestore fallaba con "Path ... not consumed"."""
    await col.insert_many([
        {"_id": "1", "Nombre comercial": "Zeta", "Clasificación": "VACUNA"},
        {"_id": "2", "Nombre comercial": "Alfa", "Clasificación": "VACUNA"},
    ])

    assert [d["_id"] for d in await col.find().sort("Nombre comercial", 1).to_list()] == ["2", "1"]
    assert {d["_id"] for d in await col.find({"Clasificación": "VACUNA"}).to_list()} == {"1", "2"}
