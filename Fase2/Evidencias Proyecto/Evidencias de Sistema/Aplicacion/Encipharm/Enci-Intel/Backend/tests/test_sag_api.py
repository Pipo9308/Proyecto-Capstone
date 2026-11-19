"""GET /sag/productos y /sag/productos/{registro}: busqueda real sobre sag_productos (RQ-09)."""
from datetime import datetime, timezone

import pytest

API = "/api/v1/sag"
NOW = datetime.now(timezone.utc)


def _producto(registro, nombre, generico, titular, fabricante="LAB X", clasificacion="ANTIPARASITARIO", status="activo"):
    return {
        "_id": registro,
        "Registro": registro,
        "Nombre comercial": nombre,
        "Nombre Genérico": generico,
        "Importador o Registrante": titular,
        "Empresa Fabricante": fabricante,
        "Clasificación": clasificacion,
        "Especies": "BOVINO",
        "status": status,
        "updated_at": NOW,
    }


@pytest.fixture
def productos(fake_db):
    fake_db.sag_productos.docs.extend([
        _producto("1001", "Draxxin", "TULATROMICINA", "ZOETIS CHILE S.A.", clasificacion="ANTIMICROBIANOS"),
        _producto("1002", "Ivermax", "IVERMECTINA", "DRAG PHARMA CHILE INVETEC S.A."),
        _producto("1003", "Ivomec Plus", "IVERMECTINA + CLORSULON", "AGROVET SPA", status="cancelado"),
    ])
    fake_db.alerts.docs.append({
        "_id": "sag_newsku_1001", "title": "Nuevo registro SAG: Draxxin", "subtype": "NEWSKU",
        "priority": "critical", "created_at": NOW,
    })


def _registros(response):
    return [p["registro"] for p in response.json()["data"]]


def test_requires_authentication(client, productos):
    assert client.get(f"{API}/productos").status_code == 401
    assert client.get(f"{API}/productos/1001").status_code == 401


def test_accepts_user_jwt_and_service_key(client, productos, user_headers, service_headers):
    assert client.get(f"{API}/productos", headers=user_headers).status_code == 200
    assert client.get(f"{API}/productos", headers=service_headers).status_code == 200


def test_search_by_commercial_name_is_case_insensitive(client, productos, service_headers):
    assert _registros(client.get(f"{API}/productos?q=draxx", headers=service_headers)) == ["1001"]


def test_search_by_active_ingredient(client, productos, service_headers):
    response = client.get(f"{API}/productos?q=ivermectina", headers=service_headers)

    assert sorted(_registros(response)) == ["1002", "1003"]
    assert response.json()["total"] == 2


def test_search_by_holder(client, productos, service_headers):
    assert _registros(client.get(f"{API}/productos?q=zoetis", headers=service_headers)) == ["1001"]


def test_search_by_registration_number(client, productos, service_headers):
    assert _registros(client.get(f"{API}/productos?q=1002", headers=service_headers)) == ["1002"]


def test_search_treats_text_literally_not_as_a_regex(client, productos, service_headers):
    response = client.get(f"{API}/productos?q=.*", headers=service_headers)

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_filter_by_status(client, productos, service_headers):
    assert _registros(client.get(f"{API}/productos?estado=cancelado", headers=service_headers)) == ["1003"]
    assert client.get(f"{API}/productos?estado=otro", headers=service_headers).status_code == 422


def test_pagination(client, productos, service_headers):
    first = client.get(f"{API}/productos?limit=2", headers=service_headers).json()
    rest = client.get(f"{API}/productos?limit=2&offset=2", headers=service_headers).json()

    assert len(first["data"]) == 2 and first["has_more"] is True and first["total"] == 3
    assert len(rest["data"]) == 1 and rest["has_more"] is False


def test_summary_shape(client, productos, service_headers):
    item = client.get(f"{API}/productos?q=draxxin", headers=service_headers).json()["data"][0]

    assert item["nombre_comercial"] == "Draxxin"
    assert item["principio_activo"] == "TULATROMICINA"
    assert item["titular"] == "ZOETIS CHILE S.A."
    assert item["clasificacion"] == "ANTIMICROBIANOS"
    assert item["estado"] == "activo"


def test_detail_includes_raw_sag_record_and_related_alerts(client, productos, service_headers):
    response = client.get(f"{API}/productos/1001", headers=service_headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["registro"] == "1001"
    assert data["registro_sag"]["Especies"] == "BOVINO"
    assert "status" not in data["registro_sag"]
    assert [a["id"] for a in data["alertas"]] == ["sag_newsku_1001"]
    assert data["alertas"][0]["prioridad"] == "critical"


def test_detail_without_alerts_returns_empty_list(client, productos, service_headers):
    assert client.get(f"{API}/productos/1002", headers=service_headers).json()["data"]["alertas"] == []


def test_detail_unknown_registration_is_404(client, productos, service_headers):
    assert client.get(f"{API}/productos/9999", headers=service_headers).status_code == 404
