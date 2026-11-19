"""Regresiones de la Fase 0: vocabulario de roles, subida de documentos y conteo de documentos."""
from types import SimpleNamespace

import pytest

from app.api.auth import get_password_hash, normalize_role
from tests.conftest import make_token

API = "/api/v1"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("admin", "admin"),
        ("Admin", "admin"),
        ("administrador", "admin"),
        ("Gerencia", "gerencia"),
        ("COMERCIAL", "comercial"),
        ("pendiente", "pendiente"),
        ("", "pendiente"),
        (None, "pendiente"),
        ("superusuario", "pendiente"),
    ],
)
def test_normalize_role(raw, expected):
    assert normalize_role(raw) == expected


def test_token_with_legacy_administrador_role_is_admin(client):
    headers = {"Authorization": f"Bearer {make_token('administrador', 'a@test.com', 'a-1')}"}
    assert client.get(f"{API}/admin/users/", headers=headers).status_code == 200


@pytest.mark.parametrize("sent, stored", [("administrador", "admin"), ("Gerencia", "gerencia"), ("comercial", "comercial")])
def test_admin_can_change_role_with_ui_or_legacy_values(client, fake_db, admin_headers, sent, stored):
    fake_db.users.docs.append({"_id": "u-1", "email": "x@test.com", "rol": "pendiente"})

    response = client.patch(f"{API}/admin/users/role", json={"email": "x@test.com", "role": sent}, headers=admin_headers)

    assert response.status_code == 200
    assert fake_db.users.docs[0]["rol"] == stored


def test_admin_cannot_set_an_unknown_role(client, fake_db, admin_headers):
    fake_db.users.docs.append({"_id": "u-1", "email": "x@test.com", "rol": "pendiente"})

    response = client.patch(f"{API}/admin/users/role", json={"email": "x@test.com", "role": "root"}, headers=admin_headers)

    assert response.status_code == 400
    assert fake_db.users.docs[0]["rol"] == "pendiente"


def test_login_returns_canonical_role_for_legacy_stored_value(client, fake_db):
    fake_db.users.docs.append(
        {"_id": "u-1", "email": "adm@test.com", "hashed_password": get_password_hash("clave-segura-1"), "rol": "administrador"}
    )

    response = client.post(f"{API}/auth/login", json={"email": "adm@test.com", "password": "clave-segura-1"})

    assert response.status_code == 200
    assert response.json()["data"]["user"]["role"] == "admin"


def test_me_returns_canonical_role(client):
    headers = {"Authorization": f"Bearer {make_token('Admin')}"}
    assert client.get(f"{API}/auth/me", headers=headers).json()["data"]["role"] == "admin"


def test_upload_rate_limit_is_keyed_by_token_subject(client, admin_headers, monkeypatch):
    """El JWT trae `sub`, no `uid`: antes la subida terminaba en KeyError -> 500."""
    seen = {}

    def fake_check(key, limit, window):
        seen["key"] = key
        return False

    monkeypatch.setattr("app.api.admin_documents.check_and_increment", fake_check)

    response = client.post(
        f"{API}/admin/documents/upload", files={"file": ("manual.txt", b"contenido", "text/plain")}, headers=admin_headers
    )

    assert response.status_code == 429
    assert seen["key"] == "upload:admin-1"


def test_docs_count_counts_distinct_documents(client, user_headers, monkeypatch):
    store = SimpleNamespace(chunk_count_by_filename=lambda: {"a.pdf": 12, "b.pdf": 3})
    monkeypatch.setattr("app.rag.engine._store", store)

    response = client.get(f"{API}/chat/docs-count", headers=user_headers)

    assert response.status_code == 200
    assert response.json()["data"]["documents"] == 2


# ── Alta de usuarios por el admin ────────────────────────────────────────────

def _nuevo(**kw):
    return {"email": "Nuevo@Test.com", "password": "clave-segura-1", "role": "comercial", **kw}


def test_admin_creates_user_with_role_and_hashed_password(client, fake_db, admin_headers):
    response = client.post(f"{API}/admin/users/", json=_nuevo(), headers=admin_headers)

    assert response.status_code == 201
    stored = fake_db.users.docs[0]
    assert stored["email"] == "nuevo@test.com" and stored["rol"] == "comercial" and stored["estado"] == "activo"
    assert stored["hashed_password"] != "clave-segura-1" and "password" not in response.text
    assert client.post(f"{API}/auth/login", json={"email": "nuevo@test.com", "password": "clave-segura-1"}).status_code == 200


def test_admin_user_creation_accepts_legacy_admin_value(client, fake_db, admin_headers):
    client.post(f"{API}/admin/users/", json=_nuevo(role="administrador"), headers=admin_headers)

    assert fake_db.users.docs[0]["rol"] == "admin"


@pytest.mark.parametrize("campos", [{"role": "root"}, {"password": "corta"}, {"email": "sin-arroba"}])
def test_user_creation_validates_input(client, fake_db, admin_headers, campos):
    assert client.post(f"{API}/admin/users/", json=_nuevo(**campos), headers=admin_headers).status_code == 400
    assert fake_db.users.docs == []


def test_user_creation_rejects_duplicates_and_non_admins(client, fake_db, admin_headers, user_headers):
    fake_db.users.docs.append({"_id": "u-1", "email": "nuevo@test.com", "rol": "pendiente"})

    assert client.post(f"{API}/admin/users/", json=_nuevo(), headers=admin_headers).status_code == 400
    assert client.post(f"{API}/admin/users/", json=_nuevo(email="otro@test.com"), headers=user_headers).status_code == 403
