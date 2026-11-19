"""RNF-01: todo endpoint pide sesion salvo /health y los de acceso a la cuenta. El test recorre las
rutas reales de la app, asi un endpoint nuevo sin proteger hace fallar el CI."""
import re

import pytest
from fastapi.routing import APIRoute

from app.core.config import Settings
from app.main import app

# Endpoints publicos a proposito (cada uno con su razon).
PUBLIC = {
    ("GET", "/health"),                          # sonda del hosting
    ("POST", "/auth/login"),                     # abre la sesion
    ("GET", "/auth/invitacion"),                 # el enlace de invitacion trae su propio token de un solo uso
    ("POST", "/auth/set-password"),              # idem
    ("POST", "/auth/forgot-password"),           # respuesta igual exista o no la cuenta
    ("POST", "/auth/register"),                  # cerrado por ALLOW_SELF_REGISTER (403)
    ("GET", "/propuestas/archivos/descarga"),    # enlace firmado que vence a los 10 minutos
}


def _routes():
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route.path


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "x", path)


@pytest.mark.parametrize("method,path", sorted(set(_routes()) - PUBLIC))
def test_every_other_endpoint_requires_a_session(client, method, path):
    response = client.request(method, _concrete(path))

    assert response.status_code == 401, f"{method} {path} respondio {response.status_code} sin sesion"


def test_the_public_list_has_no_stale_entries():
    assert PUBLIC <= set(_routes()), "hay rutas publicas declaradas que ya no existen"


def test_self_register_is_closed(client):
    response = client.post("/auth/register", json={"email": "nuevo@test.cl", "password": "ClaveInicial123"})

    assert response.status_code in (403, 404)


def test_the_root_and_readiness_are_not_public(client):
    assert client.get("/").status_code in (401, 404)
    assert client.get("/readiness").status_code == 401


def test_the_default_environment_is_production():
    """Si un despliegue olvida APP_ENV no debe quedar con /docs abierto ni errores detallados."""
    assert Settings.model_fields["APP_ENV"].default == "production"
