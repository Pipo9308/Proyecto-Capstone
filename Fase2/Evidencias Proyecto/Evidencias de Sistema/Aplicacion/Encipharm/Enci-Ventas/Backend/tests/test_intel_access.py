"""Permiso "Acceso a Inteligencia" (RQ-09 / RF-09.03).

Un usuario sin el permiso recibe 403 en /inteligencia/*; el admin lo activa por usuario
desde la gestion de usuarios. El admin siempre tiene acceso.
"""
from datetime import datetime, timezone

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models_sql.user import User

PASSWORD = "ClaveInicial123"


class _FakeIntelService:
    async def get_noticias(self):
        return [{"source": "SAG", "title": "Nuevo registro", "date": "2026-10-01", "body": "", "tags": []}]

    async def get_competencia(self):
        return {"positioning_matrix": [], "share": []}

    async def chat_query(self, question):
        return {"respuesta": "ok"}


@pytest.fixture(autouse=True)
def fake_intel(monkeypatch):
    monkeypatch.setattr("app.api.inteligencia.EnciIntelService", _FakeIntelService)


def _add_user(db, uid, email, rol, intel=False):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=email, nombre=uid.title(), rol=rol, activo=True,
        password_hash=get_password_hash(PASSWORD), webApp=True, appMovil=True,
        accesoInteligencia=intel, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _headers(user, client="web"):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}", "X-Enci-Client": client}


@pytest.fixture
def admin(db_session):
    return _add_user(db_session, "admin-1", "admin@test.cl", "admin")


@pytest.mark.parametrize("path", ["/inteligencia/noticias", "/inteligencia/competencia"])
def test_vendedor_without_permission_gets_403(client, db_session, path):
    vendedor = _add_user(db_session, "v-1", "v1@test.cl", "vendedor", intel=False)

    response = client.get(path, headers=_headers(vendedor))

    assert response.status_code == 403


def test_vendedor_without_permission_cannot_chat(client, db_session):
    vendedor = _add_user(db_session, "v-1", "v1@test.cl", "vendedor", intel=False)

    response = client.post("/inteligencia/chat", json={"pregunta": "hola"}, headers=_headers(vendedor))

    assert response.status_code == 403


def test_vendedor_with_permission_can_read_intel_from_web_and_mobile(client, db_session):
    vendedor = _add_user(db_session, "v-1", "v1@test.cl", "vendedor", intel=True)

    assert client.get("/inteligencia/noticias", headers=_headers(vendedor)).status_code == 200
    assert client.get("/inteligencia/noticias", headers=_headers(vendedor, "mobile")).status_code == 200


def test_admin_always_has_access(client, admin):
    assert client.get("/inteligencia/noticias", headers=_headers(admin)).status_code == 200


def test_unauthenticated_request_is_401(client):
    assert client.get("/inteligencia/noticias").status_code == 401


def test_admin_grants_and_revokes_permission(client, db_session, admin):
    vendedor = _add_user(db_session, "v-1", "v1@test.cl", "vendedor", intel=False)

    granted = client.patch(f"/users/{vendedor.id}", json={"accesoInteligencia": True}, headers=_headers(admin))
    assert granted.status_code == 200
    assert granted.json()["accesoInteligencia"] is True
    assert client.get("/inteligencia/noticias", headers=_headers(vendedor)).status_code == 200

    revoked = client.patch(f"/users/{vendedor.id}", json={"accesoInteligencia": False}, headers=_headers(admin))
    assert revoked.json()["accesoInteligencia"] is False
    assert client.get("/inteligencia/noticias", headers=_headers(vendedor)).status_code == 403


def test_permission_is_exposed_in_login_and_me(client, db_session):
    _add_user(db_session, "v-1", "v1@test.cl", "vendedor", intel=True)

    login = client.post("/auth/login", json={"email": "v1@test.cl", "password": PASSWORD})
    assert login.json()["user"]["accesoInteligencia"] is True

    token = login.json()["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["accesoInteligencia"] is True


def test_admin_can_create_user_with_permission(client, admin):
    payload = {
        "email": "nuevo@test.cl", "nombre": "Nuevo", "rol": "vendedor",
        "password": PASSWORD, "accesoInteligencia": True,
    }

    response = client.post("/users/", json=payload, headers=_headers(admin))

    assert response.status_code in (200, 201)
    assert response.json()["accesoInteligencia"] is True


def test_new_users_do_not_have_the_permission_by_default(client, admin):
    payload = {"email": "nuevo@test.cl", "nombre": "Nuevo", "rol": "vendedor", "password": PASSWORD}

    response = client.post("/users/", json=payload, headers=_headers(admin))

    assert response.json()["accesoInteligencia"] is False


def test_demoting_to_sin_acceso_removes_the_permission(client, db_session, admin):
    vendedor = _add_user(db_session, "v-1", "v1@test.cl", "vendedor", intel=True)

    response = client.patch(
        f"/users/{vendedor.id}", json={"rol": "sin_acceso", "accesoInteligencia": True}, headers=_headers(admin)
    )

    assert response.status_code == 200
    assert response.json()["accesoInteligencia"] is False
