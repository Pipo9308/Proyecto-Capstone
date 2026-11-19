"""Gestion de usuarios por un admin (Enci-Ventas).

Cubre hallazgos corregidos:
- Las cuentas creadas por un admin no tenian contrasena y nunca podian
  iniciar sesion.
- Degradar a "sin_acceso" y volver a promover dejaba webApp/appMovil en False
  para siempre.
- GET /users/me no existia (el frontend lo usa para validar la sesion).
"""
from datetime import datetime, timezone

import pytest

from app.core.security import create_access_token, get_password_hash
from app.models_sql.user import User

PASSWORD = "ClaveInicial123"


def _add_user(db, uid, email, rol, password=PASSWORD, web=True, mobile=True):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=email, nombre=uid.title(), rol=rol, activo=True,
        password_hash=get_password_hash(password) if password else None,
        webApp=web, appMovil=mobile, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _headers(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin(db_session):
    return _add_user(db_session, "admin-1", "admin@test.cl", "admin")


@pytest.fixture
def admin_headers(admin):
    return _headers(admin)


def _new_user_payload(**overrides):
    payload = {"email": "nuevo@test.cl", "nombre": "Nuevo Usuario", "rol": "vendedor", "password": PASSWORD}
    payload.update(overrides)
    return payload


def _login(client, email, password):
    return client.post("/auth/login", json={"email": email, "password": password})


# ── Alta con contrasena ──────────────────────────────────────────────────────

def test_create_user_without_password_creates_an_invited_account(client, admin_headers):
    """Sin contrasena la cuenta queda invitada y el admin recibe el enlace (ver test_account_invitations)."""
    payload = _new_user_payload()
    del payload["password"]

    response = client.post("/users/", json=payload, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["estado"] == "invitado"
    assert response.json()["invitacion"]["enlace"]


def test_create_user_rejects_short_password(client, admin_headers):
    resp = client.post("/users/", json=_new_user_payload(password="corta"), headers=admin_headers)
    assert resp.status_code == 422


def test_admin_created_user_can_log_in(client, admin_headers):
    created = client.post("/users/", json=_new_user_payload(), headers=admin_headers)
    assert created.status_code == 200
    assert "password" not in created.json() and "password_hash" not in created.json()

    login = _login(client, "nuevo@test.cl", PASSWORD)
    assert login.status_code == 200
    assert login.json()["user"]["email"] == "nuevo@test.cl"


def test_non_admin_cannot_create_users(client, db_session):
    seller = _add_user(db_session, "seller-1", "seller@test.cl", "vendedor")
    resp = client.post("/users/", json=_new_user_payload(), headers=_headers(seller))
    assert resp.status_code == 403


# ── Reasignar contrasena ─────────────────────────────────────────────────────

def test_admin_can_reset_a_password(client, db_session, admin_headers):
    _add_user(db_session, "seller-1", "seller@test.cl", "vendedor", password=None)
    assert _login(client, "seller@test.cl", PASSWORD).status_code == 401  # cuenta sin contrasena

    resp = client.patch("/users/seller-1/password", json={"password": "OtraClave456789"}, headers=admin_headers)
    assert resp.status_code == 200

    assert _login(client, "seller@test.cl", PASSWORD).status_code == 401
    assert _login(client, "seller@test.cl", "OtraClave456789").status_code == 200


@pytest.mark.parametrize("rol", ["vendedor", "supervisor"])
def test_only_admin_can_reset_passwords(client, db_session, rol):
    actor = _add_user(db_session, f"{rol}-1", f"{rol}@test.cl", rol)
    _add_user(db_session, "victima-1", "victima@test.cl", "vendedor")
    resp = client.patch("/users/victima-1/password", json={"password": "Hackeo123456"}, headers=_headers(actor))
    assert resp.status_code == 403
    assert _login(client, "victima@test.cl", "Hackeo123456").status_code == 401


def test_reset_password_rejects_short_password(client, db_session, admin_headers):
    _add_user(db_session, "seller-1", "seller@test.cl", "vendedor")
    resp = client.patch("/users/seller-1/password", json={"password": "abc"}, headers=admin_headers)
    assert resp.status_code == 422


def test_reset_password_for_unknown_user_is_404(client, admin_headers):
    resp = client.patch("/users/no-existe/password", json={"password": "ClaveValida123"}, headers=admin_headers)
    assert resp.status_code == 404


# ── Degradar y reactivar ─────────────────────────────────────────────────────

def test_reactivation_restores_platform_access(client, db_session, admin_headers):
    _add_user(db_session, "seller-1", "seller@test.cl", "vendedor")

    demoted = client.patch("/users/seller-1/role", json={"rol": "sin_acceso"}, headers=admin_headers)
    assert demoted.json()["webApp"] is False and demoted.json()["appMovil"] is False

    promoted = client.patch("/users/seller-1/role", json={"rol": "vendedor"}, headers=admin_headers)
    assert promoted.status_code == 200
    assert promoted.json()["webApp"] is True and promoted.json()["appMovil"] is True

    # Y de verdad puede usar la app: antes recibia 403 "sin acceso a web app".
    token = _login(client, "seller@test.cl", PASSWORD).json()["access_token"]
    me = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_admin_can_toggle_a_single_platform(client, db_session, admin_headers):
    _add_user(db_session, "seller-1", "seller@test.cl", "vendedor")
    resp = client.patch("/users/seller-1", json={"appMovil": False}, headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["appMovil"] is False
    assert resp.json()["webApp"] is True


# ── GET /users/me ────────────────────────────────────────────────────────────

def test_me_returns_own_profile_for_any_role(client, db_session):
    seller = _add_user(db_session, "seller-1", "seller@test.cl", "vendedor")
    resp = client.get("/users/me", headers=_headers(seller))
    assert resp.status_code == 200
    assert resp.json()["email"] == "seller@test.cl"
    assert resp.json()["uid"] == "seller-1"


def test_me_requires_authentication(client):
    assert client.get("/users/me").status_code == 401
