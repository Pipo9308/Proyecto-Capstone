"""Fixtures para los tests de Enci-Intel (FastAPI + MongoDB + JWT).

Las variables de entorno obligatorias se fijan ANTES de importar la app (la app
se niega a arrancar sin ellas). MongoDB se reemplaza por una base falsa en
memoria y no se ejecuta el lifespan (sin Firestore/scheduler reales).
"""
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

os.environ["JWT_SECRET_KEY"] = "test-secret-" + "x" * 40
os.environ["JWT_ALGORITHM"] = "HS256"
os.environ["FIREBASE_PROJECT_ID"] = "enci-test"
os.environ["INTEL_SERVICE_API_KEY"] = "test-service-key-" + "y" * 20
# Puerto sin servicio: los tests nunca tocan un Redis real (cache/limiter).
os.environ["REDIS_URL"] = "redis://127.0.0.1:6390/0"

# app.main hace load_dotenv(override=True) y busca .env hacia arriba (incluida la raiz del monorepo):
# sin esto un .env real pisaria las claves de prueba de arriba.
import dotenv  # noqa: E402
dotenv.load_dotenv = lambda *args, **kwargs: False

# fastembed descarga modelos de cientos de MB al usarse: no hace falta en tests.
sys.modules.setdefault("fastembed", MagicMock())

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

SERVICE_API_KEY = os.environ["INTEL_SERVICE_API_KEY"]


# ── Mongo falso en memoria ───────────────────────────────────────────────────

class _Result:
    def __init__(self, inserted_id=None):
        self.inserted_id = inserted_id


class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, *_args, **_kwargs):
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def skip(self, n):
        self._docs = self._docs[n:]
        return self

    async def to_list(self, length=None):
        return list(self._docs) if length is None else self._docs[:length]


class FakeCollection:
    def __init__(self):
        self.docs: list[dict] = []
        self._next_id = 1

    @staticmethod
    def _matches(doc, flt):
        import re

        for key, expected in (flt or {}).items():
            if key == "$or":
                if not any(FakeCollection._matches(doc, sub) for sub in expected):
                    return False
            elif isinstance(expected, dict) and "$regex" in expected:
                flags = re.IGNORECASE if "i" in expected.get("$options", "") else 0
                if not re.search(expected["$regex"], str(doc.get(key, "")), flags):
                    return False
            elif isinstance(expected, dict) and "$in" in expected:
                if doc.get(key) not in expected["$in"]:
                    return False
            elif doc.get(key) != expected:
                return False
        return True

    async def count_documents(self, flt=None):
        return sum(1 for d in self.docs if self._matches(d, flt))

    async def find_one(self, flt=None, sort=None):
        for doc in self.docs:
            if self._matches(doc, flt):
                return dict(doc)
        return None

    def find(self, flt=None):
        return _Cursor(dict(d) for d in self.docs if self._matches(d, flt))

    async def insert_one(self, doc):
        doc = dict(doc)
        doc.setdefault("_id", f"id-{self._next_id}")
        self._next_id += 1
        self.docs.append(doc)
        return _Result(doc["_id"])

    async def update_one(self, flt, update, upsert=False):
        for doc in self.docs:
            if self._matches(doc, flt):
                doc.update(update.get("$set", {}))
                return _Result()
        if upsert:
            self.docs.append({**{k: v for k, v in flt.items() if not k.startswith("$")}, **update.get("$set", {})})
        return _Result()


class FakeDB:
    def __init__(self):
        self._cols: dict[str, FakeCollection] = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._cols.setdefault(name, FakeCollection())


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_db(monkeypatch):
    import app.db as db_module

    fake = FakeDB()
    monkeypatch.setattr(db_module.db, "db", fake)
    return fake


@pytest.fixture
def client(fake_db):
    from app.main import app

    # Sin `with`: no se ejecuta el lifespan (Mongo, RAG y scheduler reales).
    return TestClient(app)


def make_token(rol="pendiente", email="user@test.com", sub="user-1", expires_in=3600):
    import jwt
    from app.api.auth import ALGORITHM, SECRET_KEY

    exp = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return jwt.encode(
        {"sub": sub, "email": email, "rol": rol, "exp": exp.timestamp()},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


@pytest.fixture
def user_headers():
    return {"Authorization": f"Bearer {make_token('Comercial')}"}


@pytest.fixture
def admin_headers():
    return {"Authorization": f"Bearer {make_token('admin', 'admin@test.com', 'admin-1')}"}


@pytest.fixture
def service_headers():
    return {"X-API-Key": SERVICE_API_KEY}
