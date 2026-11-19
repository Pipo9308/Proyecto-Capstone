"""Ventas como intermediario de Enci-Intel (RQ-09): alertas, lecturas por usuario y fichas SAG."""
from datetime import datetime, timezone

import httpx
import pytest

from app.core.security import create_access_token, get_password_hash
from app.models_sql.user import User
from app.services import enci_intel

ALERTS = [
    {"id": "sag_newsku_1001", "title": "Nuevo registro SAG: Draxxin", "priority": "critical", "competitor": "ZOETIS"},
    {"id": "comp_noticia_ab", "title": "Nueva publicación Drag Pharma: X", "priority": "medium", "competitor": "Drag Pharma"},
]
COUNTS = {"total": 2, "critical": 1, "high": 0, "medium": 1, "low": 0}


class FakeIntel:
    """Servidor de Enci-Intel falso: registra las peticiones y responde segun la ruta."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.status_override: int | None = None
        self.raise_error: Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raise_error:
            raise self.raise_error
        if self.status_override:
            return httpx.Response(self.status_override, json={"detail": "x"})
        path = request.url.path
        if path == "/api/v1/alerts/":
            return httpx.Response(200, json={
                "success": True, "counts": COUNTS, "total": 2, "limit": 50, "offset": 0,
                "has_more": False, "data": [dict(a) for a in ALERTS],
            })
        if path.startswith("/api/v1/alerts/"):
            alert_id = path.rsplit("/", 1)[1]
            match = next((a for a in ALERTS if a["id"] == alert_id), None)
            if not match:
                return httpx.Response(404, json={"detail": "Alerta no encontrada"})
            return httpx.Response(200, json={"success": True, "data": dict(match)})
        if path == "/api/v1/sag/productos":
            return httpx.Response(200, json={"success": True, "total": 1, "limit": 20, "offset": 0, "has_more": False,
                                              "data": [{"registro": "1001", "nombre_comercial": "Draxxin"}]})
        if path == "/api/v1/sag/productos/1001":
            return httpx.Response(200, json={"success": True, "data": {
                "registro": "1001", "nombre_comercial": "Draxxin", "titular": "ZOETIS CHILE S.A.",
                "actualizado": "2026-10-01T10:00:00+00:00", "registro_sag": {"Especies": "BOVINO"},
                "alertas": [{"id": "sag_newsku_1001", "titulo": "Nuevo registro SAG: Draxxin"}],
            }})
        if path.startswith("/api/v1/sag/productos/"):
            return httpx.Response(404, json={"detail": "Registro SAG no encontrado"})
        return httpx.Response(404)


@pytest.fixture
def intel(monkeypatch):
    fake = FakeIntel()
    monkeypatch.setattr(enci_intel.settings, "ENCI_INTEL_API_URL", "http://intel.test")
    monkeypatch.setattr(enci_intel.settings, "ENCI_INTEL_API_KEY", "clave-de-servicio")

    def _client(self):
        return httpx.AsyncClient(base_url=self.base_url, headers=self.headers, transport=httpx.MockTransport(fake.handler))

    monkeypatch.setattr(enci_intel.EnciIntelService, "_get_client", _client)
    return fake


def _add_user(db, uid, rol="vendedor", intel_access=True):
    now = datetime.now(timezone.utc)
    user = User(
        id=uid, email=f"{uid}@test.cl", nombre=uid.title(), rol=rol, activo=True,
        password_hash=get_password_hash("ClaveInicial123"), webApp=True, appMovil=True,
        accesoInteligencia=intel_access, createdAt=now, updatedAt=now,
    )
    db.add(user)
    db.commit()
    return user


def _headers(user, client="web"):
    token = create_access_token(data={"sub": user.email, "uid": user.id, "rol": user.rol})
    return {"Authorization": f"Bearer {token}", "X-Enci-Client": client}


@pytest.fixture
def vendedor(db_session):
    return _add_user(db_session, "v-1")


# ── Alertas ──────────────────────────────────────────────────────────────────

def test_alerts_forward_filters_and_service_key(client, intel, vendedor):
    response = client.get(
        "/inteligencia/alertas?priority=critical&type=NEWSKU&competitor=zoetis&limit=10&offset=20",
        headers=_headers(vendedor),
    )

    assert response.status_code == 200
    sent = intel.requests[0]
    assert sent.headers["X-API-Key"] == "clave-de-servicio"
    assert dict(sent.url.params) == {"priority": "critical", "type": "NEWSKU", "competitor": "zoetis", "limit": "10", "offset": "20"}


def test_alerts_are_marked_unread_by_default(client, intel, vendedor):
    body = client.get("/inteligencia/alertas", headers=_headers(vendedor)).json()

    assert [a["leida"] for a in body["data"]] == [False, False]
    assert body["counts"]["total"] == 2


def test_mark_alert_as_read_is_idempotent_and_per_user(client, intel, db_session, vendedor):
    otro = _add_user(db_session, "v-2")

    first = client.patch("/inteligencia/alertas/sag_newsku_1001/leida", headers=_headers(vendedor))
    again = client.patch("/inteligencia/alertas/sag_newsku_1001/leida", headers=_headers(vendedor))
    mine = client.get("/inteligencia/alertas", headers=_headers(vendedor)).json()["data"]
    theirs = client.get("/inteligencia/alertas", headers=_headers(otro)).json()["data"]

    assert first.status_code == again.status_code == 200
    assert first.json() == {"alertId": "sag_newsku_1001", "leida": True}
    assert {a["id"]: a["leida"] for a in mine} == {"sag_newsku_1001": True, "comp_noticia_ab": False}
    assert all(a["leida"] is False for a in theirs)


def test_unread_count(client, intel, vendedor):
    assert client.get("/inteligencia/alertas/no-leidas", headers=_headers(vendedor)).json() == {"no_leidas": 2}

    client.patch("/inteligencia/alertas/comp_noticia_ab/leida", headers=_headers(vendedor))

    assert client.get("/inteligencia/alertas/no-leidas", headers=_headers(vendedor)).json() == {"no_leidas": 1}


def test_alert_detail_includes_read_state(client, intel, vendedor):
    before = client.get("/inteligencia/alertas/sag_newsku_1001", headers=_headers(vendedor)).json()
    client.patch("/inteligencia/alertas/sag_newsku_1001/leida", headers=_headers(vendedor))
    after = client.get("/inteligencia/alertas/sag_newsku_1001", headers=_headers(vendedor)).json()

    assert before["data"]["leida"] is False
    assert after["data"]["leida"] is True


def test_unknown_alert_is_404_and_cannot_be_marked(client, intel, vendedor):
    assert client.get("/inteligencia/alertas/no-existe", headers=_headers(vendedor)).status_code == 404
    assert client.patch("/inteligencia/alertas/no-existe/leida", headers=_headers(vendedor)).status_code == 404


def test_alert_ids_with_unsafe_characters_are_rejected(client, intel, vendedor):
    response = client.get("/inteligencia/alertas/..%2F..%2Fadmin", headers=_headers(vendedor))

    assert response.status_code in (404, 422)
    assert intel.requests == []


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "offset=-1"])
def test_alert_pagination_is_bounded(client, intel, vendedor, query):
    assert client.get(f"/inteligencia/alertas?{query}", headers=_headers(vendedor)).status_code == 422


# ── Productos SAG ────────────────────────────────────────────────────────────

def test_product_search_is_proxied(client, intel, vendedor):
    response = client.get("/inteligencia/productos?q=draxxin", headers=_headers(vendedor))

    assert response.status_code == 200
    assert response.json()["data"][0]["registro"] == "1001"
    assert dict(intel.requests[0].url.params)["q"] == "draxxin"


def test_product_sheet_has_sources_and_empty_prices(client, intel, vendedor):
    response = client.get("/inteligencia/productos/1001/ficha", headers=_headers(vendedor))

    assert response.status_code == 200
    ficha = response.json()["data"]
    assert ficha["registro"] == "1001"
    assert ficha["precios"] == []
    assert ficha["equivalente_encipharm"] is None
    assert ficha["alertas"][0]["id"] == "sag_newsku_1001"
    assert {"dato": "registro_sag", "origen": "SAG (Enci-Intel)", "fecha": "2026-10-01T10:00:00+00:00"} in ficha["fuentes"]


def test_product_sheet_includes_approved_prices_and_equivalent_by_sag_registry(client, intel, vendedor, db_session):
    from datetime import date
    from app.models_sql.competencia import EquivalenciaProducto, PrecioCompetencia, ProductoCompetencia, ProductoEncipharm

    enci = ProductoEncipharm(nombre="Draxcin", principiosActivos="", unidadMedida="ml", cantidadPresentacion=100)
    comp = ProductoCompetencia(
        competidor="Zoetis", nombre="Draxxin", presentacion="100 ml", principiosActivos="", unidadMedida="ml",
        cantidadPresentacion=100, registroSag="1001",
    )
    db_session.add_all([enci, comp])
    db_session.flush()
    db_session.add(EquivalenciaProducto(id=f"{comp.id}:{enci.id}", productoCompetenciaId=comp.id, productoEncipharmId=enci.id))
    for precio, estado in ((90000, "aprobado"), (1, "pendiente")):
        db_session.add(PrecioCompetencia(
            productoId=comp.id, precio=precio, estado=estado, reportadoPor=vendedor.id, fechaPrecio=date(2026, 10, 1),
        ))
    db_session.commit()

    ficha = client.get("/inteligencia/productos/1001/ficha", headers=_headers(vendedor)).json()["data"]

    assert [(p["precio"], p["precioPorUnidad"], p["fecha"]) for p in ficha["precios"]] == [(90000.0, 900.0, "2026-10-01")]
    assert ficha["equivalente_encipharm"] == {"nombre": "Draxcin"}


def test_unknown_product_sheet_is_404(client, intel, vendedor):
    assert client.get("/inteligencia/productos/9999/ficha", headers=_headers(vendedor)).status_code == 404


# ── Permisos y degradacion ───────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/inteligencia/alertas", "/inteligencia/alertas/no-leidas", "/inteligencia/productos?q=a",
                                  "/inteligencia/productos/1001/ficha"])
def test_new_endpoints_require_intel_access(client, intel, db_session, path):
    sin_permiso = _add_user(db_session, "v-9", intel_access=False)

    assert client.get(path, headers=_headers(sin_permiso)).status_code == 403
    assert intel.requests == []


def test_mark_read_requires_intel_access(client, intel, db_session):
    sin_permiso = _add_user(db_session, "v-9", intel_access=False)

    assert client.patch("/inteligencia/alertas/sag_newsku_1001/leida", headers=_headers(sin_permiso)).status_code == 403


def test_intel_rejecting_the_service_key_does_not_log_the_user_out(client, intel, vendedor):
    """Un 401 de Intel es un problema de configuracion: llegar como 401 cerraria la sesion web."""
    intel.status_override = 401

    response = client.get("/inteligencia/alertas", headers=_headers(vendedor))

    assert response.status_code == 502


def test_intel_server_error_is_502(client, intel, vendedor):
    intel.status_override = 500

    assert client.get("/inteligencia/alertas", headers=_headers(vendedor)).status_code == 502


@pytest.mark.parametrize("error", [httpx.ConnectTimeout("lento"), httpx.ConnectError("caido")])
def test_intel_down_is_503_with_a_clear_message(client, intel, vendedor, error):
    intel.raise_error = error

    response = client.get("/inteligencia/alertas", headers=_headers(vendedor))

    assert response.status_code == 503
    assert "Enci-Intel" in response.json()["error"]


def test_missing_intel_url_is_503(client, intel, vendedor, monkeypatch):
    monkeypatch.setattr(enci_intel.settings, "ENCI_INTEL_API_URL", None)

    assert client.get("/inteligencia/alertas", headers=_headers(vendedor)).status_code == 503
