"""Usuarios con invitacion por enlace (RQ-05): crear cuenta sin contrasena, activarla con un
enlace de un solo uso (72 h), restablecer, politica de contrasena y registro publico cerrado."""
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.config import get_settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models_sql.account_token import AccountToken
from app.models_sql.user import User

PASSWORD = "ClaveInicial123"
NEW_PASSWORD = "NuevaClave2026"


def _add_user(db, uid, rol="vendedor", password=PASSWORD, activo=True):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.title(), rol=rol, activo=activo,
        password_hash=get_password_hash(password) if password else None,
        webApp=True, appMovil=True, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _headers(user):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}"}


def _token_of(link):
    return parse_qs(urlparse(link).query)["token"][0]


@pytest.fixture
def admin(db_session):
    return _add_user(db_session, "admin-1", rol="admin")


def invite(client, admin, email="nuevo@test.cl", **extra):
    payload = {"email": email, "nombre": "Nuevo Usuario", "rol": "vendedor", **extra}
    return client.post("/users/", json=payload, headers=_headers(admin))


# ── Invitar ──────────────────────────────────────────────────────────────────

def test_admin_invites_a_user_and_gets_a_link_valid_for_72_hours(client, admin):
    response = invite(client, admin)

    body = response.json()
    assert response.status_code == 200
    assert body["estado"] == "invitado" and body["activo"] is True
    assert body["invitacion"]["tipo"] == "invitacion"
    assert body["invitacion"]["enlace"].startswith(f"{get_settings().FRONTEND_URL}/activar?token=")
    expires = datetime.fromisoformat(body["invitacion"]["expiraEn"])
    assert timedelta(hours=71, minutes=59) < expires - datetime.utcnow() < timedelta(hours=72, minutes=1)


def test_the_database_stores_only_a_hash_of_the_token(client, admin, db_session):
    raw = _token_of(invite(client, admin).json()["invitacion"]["enlace"])

    stored = db_session.query(AccountToken).one()

    assert stored.tokenHash != raw and len(stored.tokenHash) == 64


def test_a_user_created_with_a_password_is_active_and_gets_no_link(client, admin):
    body = invite(client, admin, password=PASSWORD).json()

    assert body["estado"] == "activo" and body["invitacion"] is None


def test_an_invited_user_cannot_log_in_until_they_create_a_password(client, admin):
    invite(client, admin)

    response = client.post("/auth/login", json={"email": "nuevo@test.cl", "password": PASSWORD})

    assert response.status_code == 401


# ── Activar ──────────────────────────────────────────────────────────────────

def test_preview_shows_who_the_link_is_for_without_consuming_it(client, admin):
    link = invite(client, admin).json()["invitacion"]["enlace"]
    token = _token_of(link)

    first = client.get("/auth/invitacion", params={"token": token})
    second = client.get("/auth/invitacion", params={"token": token})

    assert first.status_code == second.status_code == 200
    assert first.json()["email"] == "nuevo@test.cl" and first.json()["tipo"] == "invitacion"


def test_creating_the_password_logs_the_user_in_and_activates_the_account(client, admin, db_session):
    token = _token_of(invite(client, admin).json()["invitacion"]["enlace"])

    response = client.post("/auth/set-password", json={"token": token, "password": NEW_PASSWORD})

    assert response.status_code == 200
    session = response.json()
    assert session["access_token"] and session["user"]["estado"] == "activo"
    me = client.get("/users/me", headers={"Authorization": f"Bearer {session['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "nuevo@test.cl"
    assert client.post("/auth/login", json={"email": "nuevo@test.cl", "password": NEW_PASSWORD}).status_code == 200


def test_a_link_works_only_once(client, admin):
    token = _token_of(invite(client, admin).json()["invitacion"]["enlace"])
    client.post("/auth/set-password", json={"token": token, "password": NEW_PASSWORD})

    again = client.post("/auth/set-password", json={"token": token, "password": "OtraClave12345"})
    preview = client.get("/auth/invitacion", params={"token": token})

    assert again.status_code == 400 and again.json()["codigo"] == "ERR_ENLACE_INVALIDO"
    assert preview.status_code == 400
    assert client.post("/auth/login", json={"email": "nuevo@test.cl", "password": "OtraClave12345"}).status_code == 401


def test_an_expired_link_is_rejected_with_a_specific_code(client, admin, db_session):
    token = _token_of(invite(client, admin).json()["invitacion"]["enlace"])
    stored = db_session.query(AccountToken).one()
    stored.expiresAt = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()

    response = client.post("/auth/set-password", json={"token": token, "password": NEW_PASSWORD})

    assert response.status_code == 400 and response.json()["codigo"] == "ERR_ENLACE_EXPIRADO"


@pytest.mark.parametrize("token", ["x" * 43, "no-existe-este-token-0123456789"])
def test_unknown_tokens_are_rejected(client, token):
    assert client.post("/auth/set-password", json={"token": token, "password": NEW_PASSWORD}).status_code == 400
    assert client.get("/auth/invitacion", params={"token": token}).status_code == 400


def test_a_new_link_invalidates_the_previous_one(client, admin, db_session):
    first = _token_of(invite(client, admin).json()["invitacion"]["enlace"])
    uid = db_session.query(User).filter(User.email == "nuevo@test.cl").one().id

    second = _token_of(client.post(f"/users/{uid}/invitacion", headers=_headers(admin)).json()["enlace"])

    assert client.post("/auth/set-password", json={"token": first, "password": NEW_PASSWORD}).status_code == 400
    assert client.post("/auth/set-password", json={"token": second, "password": NEW_PASSWORD}).status_code == 200


def test_a_deactivated_user_cannot_activate_their_account(client, admin, db_session):
    token = _token_of(invite(client, admin).json()["invitacion"]["enlace"])
    user = db_session.query(User).filter(User.email == "nuevo@test.cl").one()
    user.activo = False
    db_session.commit()

    assert client.post("/auth/set-password", json={"token": token, "password": NEW_PASSWORD}).status_code == 403


# ── Politica de contrasena ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    "password, reason",
    [("Corta1", "10 caracteres"), ("soloLetrasAqui", "letras y numeros"), ("1234567890123", "letras y numeros"), ("a1" * 40, "larga")],
)
def test_weak_passwords_are_rejected_everywhere(client, admin, password, reason):
    token = _token_of(invite(client, admin).json()["invitacion"]["enlace"])
    uid = client.get("/users/", headers=_headers(admin)).json()[-1]["uid"]

    by_link = client.post("/auth/set-password", json={"token": token, "password": password})
    by_admin = client.patch(f"/users/{uid}/password", json={"password": password}, headers=_headers(admin))
    on_create = invite(client, admin, email="otro@test.cl", password=password)

    for response in (by_link, by_admin, on_create):
        assert response.status_code == 422
        assert reason in str(response.json()["detalles"])


def test_a_password_longer_than_bcrypt_allows_does_not_crash_login(client, admin):
    response = client.post("/auth/login", json={"email": "admin-1@test.cl", "password": "a1" * 60})

    assert response.status_code == 401


def test_verify_password_returns_false_for_over_long_passwords():
    assert verify_password("a" * 100, get_password_hash("Valida12345")) is False


# ── Restablecer ──────────────────────────────────────────────────────────────

def test_forgot_password_answers_the_same_whether_or_not_the_account_exists(client, db_session):
    _add_user(db_session, "real")

    known = client.post("/auth/forgot-password", json={"email": "real@test.cl"})
    unknown = client.post("/auth/forgot-password", json={"email": "nadie@test.cl"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_forgot_password_flags_the_request_for_the_admin_who_then_sends_a_link(client, admin, db_session):
    user = _add_user(db_session, "real")
    client.post("/auth/forgot-password", json={"email": "real@test.cl"})

    listing = {u["email"]: u for u in client.get("/users/", headers=_headers(admin)).json()}
    assert listing["real@test.cl"]["restablecimientoSolicitado"] is True
    assert listing["admin-1@test.cl"]["restablecimientoSolicitado"] is False

    link = client.post(f"/users/{user.id}/invitacion", headers=_headers(admin)).json()
    assert link["tipo"] == "reset"
    client.post("/auth/set-password", json={"token": _token_of(link["enlace"]), "password": NEW_PASSWORD})

    db_session.refresh(user)
    assert verify_password(NEW_PASSWORD, user.password_hash)
    assert user.passwordResetRequestedAt is None
    assert client.post("/auth/login", json={"email": "real@test.cl", "password": PASSWORD}).status_code == 401


def test_forgot_password_ignores_invited_and_deactivated_accounts(client, admin, db_session):
    _add_user(db_session, "invitado", password=None)
    _add_user(db_session, "baja", activo=False)

    for email in ("invitado@test.cl", "baja@test.cl"):
        client.post("/auth/forgot-password", json={"email": email})

    flags = {u["email"]: u["restablecimientoSolicitado"] for u in client.get("/users/", headers=_headers(admin)).json()}
    assert flags["invitado@test.cl"] is False and flags["baja@test.cl"] is False


# ── Permisos y estados ───────────────────────────────────────────────────────

def test_only_an_admin_can_generate_links(client, db_session):
    vendedor = _add_user(db_session, "vend-1")
    target = _add_user(db_session, "otro", password=None)

    assert client.post(f"/users/{target.id}/invitacion", headers=_headers(vendedor)).status_code == 403
    assert client.post(f"/users/{target.id}/invitacion").status_code == 401


def test_cannot_generate_a_link_for_an_unknown_or_deactivated_user(client, admin, db_session):
    baja = _add_user(db_session, "baja", activo=False)

    assert client.post("/users/no-existe/invitacion", headers=_headers(admin)).status_code == 404
    assert client.post(f"/users/{baja.id}/invitacion", headers=_headers(admin)).status_code == 400


def test_users_are_listed_with_their_state(client, admin, db_session):
    _add_user(db_session, "invitado", password=None)
    _add_user(db_session, "baja", activo=False)

    states = {u["email"]: u["estado"] for u in client.get("/users/", headers=_headers(admin)).json()}

    assert states == {"admin-1@test.cl": "activo", "invitado@test.cl": "invitado", "baja@test.cl": "desactivado"}


def test_deactivating_blocks_access_immediately(client, admin, db_session):
    user = _add_user(db_session, "vend-1")
    token = client.post("/auth/login", json={"email": "vend-1@test.cl", "password": PASSWORD}).json()["access_token"]
    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200

    client.patch(f"/users/{user.id}/status", json={"activo": False}, headers=_headers(admin))

    assert client.get("/users/me", headers={"Authorization": f"Bearer {token}"}).status_code == 403


# ── Registro publico ─────────────────────────────────────────────────────────

def test_public_registration_is_closed_by_default(client, db_session):
    response = client.post("/auth/register", json={"email": "intruso@test.cl", "password": PASSWORD})

    assert response.status_code == 403
    assert db_session.query(User).count() == 0


def test_registration_can_be_reenabled_explicitly(client, db_session, monkeypatch):
    monkeypatch.setattr(get_settings(), "ALLOW_SELF_REGISTER", True)

    response = client.post("/auth/register", json={"email": "nuevo@test.cl", "password": PASSWORD})

    assert response.status_code == 200 and response.json()["user"]["rol"] == "sin_acceso"
