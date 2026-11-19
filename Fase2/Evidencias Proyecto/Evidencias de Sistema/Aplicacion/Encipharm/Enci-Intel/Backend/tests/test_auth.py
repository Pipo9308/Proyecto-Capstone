"""Autenticacion y autorizacion de Enci-Intel.

Cubre los hallazgos criticos corregidos: registro con rol arbitrario
(escalacion de privilegios), endpoints de lectura sin autenticacion y
arranque con secretos inseguros.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import make_token

BACKEND_ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1"


# ── Registro: el rol nunca lo decide el cliente ──────────────────────────────

def test_register_ignores_client_supplied_role(client, fake_db):
    resp = client.post(
        f"{API}/auth/register",
        json={"email": "atacante@test.com", "password": "clave-larga-123", "rol": "admin"},
    )
    assert resp.status_code == 200

    stored = next(d for d in fake_db.users.docs if d["email"] == "atacante@test.com")
    assert stored["rol"] == "pendiente"


def test_registered_user_cannot_log_in_until_approved(client):
    client.post(f"{API}/auth/register", json={"email": "a@test.com", "password": "clave-larga-123", "rol": "Admin"})
    login = client.post(f"{API}/auth/login", json={"email": "a@test.com", "password": "clave-larga-123"})

    assert login.status_code == 403 and "pendiente" in login.json()["detail"]
    assert "token" not in login.text
    mala = client.post(f"{API}/auth/login", json={"email": "a@test.com", "password": "otra-clave-123"})
    assert mala.status_code == 401  # la clave incorrecta no revela que la cuenta existe y esta pendiente


def test_a_pending_token_issued_before_is_rejected_everywhere(client):
    pendiente = {"Authorization": f"Bearer {make_token('pendiente')}"}

    for ruta in ("/alerts/", "/agents/", "/market/share", "/sag/productos", "/auth/me", "/chat/docs-count"):
        assert client.get(f"{API}{ruta}", headers=pendiente).status_code == 403, ruta
    chat = client.post(f"{API}/chat/stream", json={"question": "hola"}, headers=pendiente)
    assert chat.status_code == 403


def test_register_rejects_duplicate_email(client):
    body = {"email": "dup@test.com", "password": "clave-larga-123"}
    assert client.post(f"{API}/auth/register", json=body).status_code == 200
    assert client.post(f"{API}/auth/register", json=body).status_code == 400


def test_login_rejects_wrong_password(client):
    client.post(f"{API}/auth/register", json={"email": "u@test.com", "password": "clave-larga-123"})
    resp = client.post(f"{API}/auth/login", json={"email": "u@test.com", "password": "otra-clave"})
    assert resp.status_code == 401


def test_admin_can_list_users(client, admin_headers):
    assert client.get(f"{API}/admin/users/", headers=admin_headers).status_code == 200


# ── Endpoints de lectura: exigen autenticacion ───────────────────────────────

PROTECTED_GET = [
    "/market/share",
    "/market/import-trends",
    "/market/positioning-matrix",
    "/market/news",
    "/products/",
    "/alerts/",
    "/agents/",
    "/dashboard/summary",
    "/chat/docs-count",
]


@pytest.mark.parametrize("path", PROTECTED_GET)
def test_read_endpoints_reject_anonymous(client, path):
    assert client.get(f"{API}{path}").status_code == 401


def test_chat_query_rejects_anonymous(client):
    assert client.post(f"{API}/chat/query", json={"question": "hola"}).status_code == 401


@pytest.mark.parametrize("path", PROTECTED_GET)
def test_read_endpoints_reject_garbage_token(client, path):
    resp = client.get(f"{API}{path}", headers={"Authorization": "Bearer no-es-un-jwt"})
    assert resp.status_code == 401


def test_expired_token_is_rejected(client):
    expired = make_token("admin", expires_in=-60)
    resp = client.get(f"{API}/market/share", headers={"Authorization": f"Bearer {expired}"})
    assert resp.status_code == 401


# ── require_user_or_service: JWT o API key de servicio ───────────────────────

MARKET_SERVICE_PATHS = ["/market/share", "/market/import-trends", "/market/positioning-matrix", "/market/news"]


@pytest.mark.parametrize("path", MARKET_SERVICE_PATHS)
def test_market_accepts_user_jwt(client, user_headers, path):
    assert client.get(f"{API}{path}", headers=user_headers).status_code == 200


@pytest.mark.parametrize("path", MARKET_SERVICE_PATHS)
def test_market_accepts_service_api_key(client, service_headers, path):
    assert client.get(f"{API}{path}", headers=service_headers).status_code == 200


@pytest.mark.parametrize("path", MARKET_SERVICE_PATHS)
def test_market_rejects_wrong_api_key(client, path):
    assert client.get(f"{API}{path}", headers={"X-API-Key": "clave-incorrecta"}).status_code == 401


def test_service_key_does_not_open_user_only_endpoints(client, service_headers):
    """La API key de servicio solo vale donde el proxy la necesita."""
    assert client.get(f"{API}/agents/", headers=service_headers).status_code == 401
    assert client.get(f"{API}/dashboard/summary", headers=service_headers).status_code == 401


def test_user_jwt_opens_user_endpoints(client, user_headers):
    assert client.get(f"{API}/agents/", headers=user_headers).status_code == 200
    assert client.get(f"{API}/products/", headers=user_headers).status_code == 200


def test_non_admin_cannot_run_agents(client, user_headers):
    assert client.post(f"{API}/agents/agente_sag/run", headers=user_headers).status_code == 403


# ── Arranque: se niega a iniciar con secretos inseguros ──────────────────────

def _import_with_env(module: str, **env_overrides) -> subprocess.CompletedProcess:
    env = {**os.environ, **env_overrides}
    for key, value in list(env.items()):
        if value is None:
            env.pop(key)
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=BACKEND_ROOT, env=env, capture_output=True, text=True, timeout=60,
    )


@pytest.mark.parametrize(
    "secret",
    ["", "corto", "change_this_to_a_secure_random_key", "change_this_" + "x" * 40],
)
def test_app_refuses_to_start_with_insecure_jwt_secret(secret):
    result = _import_with_env("app.api.auth", JWT_SECRET_KEY=secret)
    assert result.returncode != 0
    assert "JWT_SECRET_KEY" in result.stderr


def test_app_accepts_a_strong_jwt_secret():
    assert _import_with_env("app.api.auth", JWT_SECRET_KEY="k" * 48).returncode == 0


def test_app_refuses_to_start_without_firebase_project_id():
    result = _import_with_env("app.db", FIREBASE_PROJECT_ID="")
    assert result.returncode != 0
    assert "FIREBASE_PROJECT_ID" in result.stderr
