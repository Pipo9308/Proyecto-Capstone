"""Fixtures de Ventas. Los tests corren contra el EMULADOR de Cloud Firestore (FIRESTORE_EMULATOR_HOST):

    docker run -p 8085:8085 gcr.io/google.com/cloudsdktool/google-cloud-cli:emulators \
        gcloud emulators firestore start --host-port=0.0.0.0:8085
    FIRESTORE_EMULATOR_HOST=localhost:8085 FIREBASE_PROJECT_ID=enci-test JWT_SECRET=... pytest

Antes de cada test se vacia el emulador, asi que cada uno parte de una base limpia.
"""
import os
import sys
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("FIREBASE_PROJECT_ID", "enci-test")
if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
    pytest.exit("Los tests de Ventas necesitan el emulador de Firestore: defina FIRESTORE_EMULATOR_HOST", returncode=2)

# Ahora podemos importar de la app
from app.main import app  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.odm import new_session  # noqa: E402


def _clear_emulator() -> None:
    host, project = os.environ["FIRESTORE_EMULATOR_HOST"], os.environ["FIREBASE_PROJECT_ID"]
    httpx.delete(f"http://{host}/emulator/v1/projects/{project}/databases/(default)/documents", timeout=30).raise_for_status()


@pytest.fixture
def setup_db():
    """Sin tablas que crear: se mantiene el nombre porque otros fixtures y tests lo piden."""
    _clear_emulator()
    yield


@pytest.fixture
def db_session(setup_db):
    db = new_session()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    original_audit_factory = app.state.audit_session_factory
    app.state.audit_session_factory = new_session
    # El limitador global (120/min por IP, contador en Redis) haria inestables los tests:
    # corridas seguidas comparten el contador y una suite grande supera el limite sola.
    app.state.limiter.enabled = False
    with TestClient(app) as test_client:
        yield test_client
    app.state.limiter.enabled = True
    app.state.audit_session_factory = original_audit_factory
    app.dependency_overrides.clear()
