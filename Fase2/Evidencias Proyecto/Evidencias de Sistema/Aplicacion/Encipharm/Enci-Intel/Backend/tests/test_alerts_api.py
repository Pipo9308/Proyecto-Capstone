"""GET /alerts/ y /alerts/{id}: filtros, paginacion y acceso por API key de servicio (RQ-09)."""
from datetime import datetime, timedelta, timezone

import pytest

API = "/api/v1"
NOW = datetime.now(timezone.utc)


def _alert(alert_id, *, priority="medium", subtype="NOTICIA", agent="agente_competidores", minutes=0,
           data=None, title=None, expired=False):
    return {
        "_id": alert_id,
        "title": title or f"Alerta {alert_id}",
        "type": "REGULATORY" if agent == "agente_sag" else "LAUNCH",
        "subtype": subtype,
        "priority": priority,
        "urgency": {"critical": 90, "high": 70, "medium": 50, "low": 10}[priority],
        "source": "SAG" if agent == "agente_sag" else "Web competidor",
        "agent_id": agent,
        "status": "active",
        "created_at": NOW - timedelta(minutes=minutes),
        "expires_at": NOW + timedelta(days=-1 if expired else 7),
        "data": data or {},
    }


@pytest.fixture
def alerts(fake_db):
    fake_db.alerts.docs.extend([
        _alert("a1", priority="critical", subtype="NEWSKU", agent="agente_sag", minutes=1,
               data={"Importador o Registrante": "ZOETIS CHILE S.A.", "Nombre comercial": "Draxxin"}),
        _alert("a2", priority="high", subtype="CANCELACION", agent="agente_sag", minutes=2,
               data={"registro": "R-2", "empresa": "AGROVET MARKET"}),
        _alert("a3", priority="medium", subtype="NOTICIA", minutes=3,
               data={"empresa": "DRAG PHARMA", "url": "https://dragpharma.cl/x"}),
        _alert("a4", priority="medium", subtype="NOTICIA", minutes=4,
               title="Nueva publicación Drag Pharma: Lanzamiento"),
        _alert("a5", priority="low", subtype="NOTICIA", minutes=5, data={"empresa": "DRAG PHARMA"}),
        _alert("viejo", priority="critical", subtype="NEWSKU", agent="agente_sag", minutes=6, expired=True),
    ])


def _ids(response):
    return [a["id"] for a in response.json()["data"]]


def test_anonymous_is_rejected(client, alerts):
    assert client.get(f"{API}/alerts/").status_code == 401


def test_user_jwt_and_service_key_can_read(client, alerts, user_headers, service_headers):
    assert client.get(f"{API}/alerts/", headers=user_headers).status_code == 200
    assert client.get(f"{API}/alerts/", headers=service_headers).status_code == 200


def test_wrong_service_key_is_rejected(client, alerts):
    assert client.get(f"{API}/alerts/", headers={"X-API-Key": "incorrecta"}).status_code == 401


def test_expired_alerts_are_included_and_newest_first(client, alerts, service_headers):
    body = client.get(f"{API}/alerts/", headers=service_headers).json()

    assert [a["id"] for a in body["data"]] == ["a1", "a2", "a3", "a4", "a5", "viejo"]
    assert body["total"] == 6
    assert body["has_more"] is False


def test_pagination_with_limit_and_offset(client, alerts, service_headers):
    first = client.get(f"{API}/alerts/?limit=2", headers=service_headers).json()
    second = client.get(f"{API}/alerts/?limit=2&offset=2", headers=service_headers).json()
    last = client.get(f"{API}/alerts/?limit=2&offset=4", headers=service_headers).json()

    assert [a["id"] for a in first["data"]] == ["a1", "a2"] and first["has_more"] is True
    assert [a["id"] for a in second["data"]] == ["a3", "a4"] and second["has_more"] is True
    assert [a["id"] for a in last["data"]] == ["a5", "viejo"] and last["has_more"] is False
    assert first["total"] == second["total"] == last["total"] == 6


def test_limit_is_bounded(client, alerts, service_headers):
    assert client.get(f"{API}/alerts/?limit=0", headers=service_headers).status_code == 422
    assert client.get(f"{API}/alerts/?limit=1000", headers=service_headers).status_code == 422
    assert client.get(f"{API}/alerts/?offset=-1", headers=service_headers).status_code == 422


def test_filter_by_priority(client, alerts, service_headers):
    response = client.get(f"{API}/alerts/?priority=medium", headers=service_headers)

    assert _ids(response) == ["a3", "a4"]
    assert response.json()["total"] == 2


def test_filter_by_type_matches_subtype_case_insensitively(client, alerts, service_headers):
    assert _ids(client.get(f"{API}/alerts/?type=cancelacion", headers=service_headers)) == ["a2"]
    assert _ids(client.get(f"{API}/alerts/?type=NEWSKU", headers=service_headers)) == ["a1", "viejo"]


def test_filter_by_competitor_uses_data_or_title(client, alerts, service_headers):
    drag = client.get(f"{API}/alerts/?competitor=drag", headers=service_headers)
    zoetis = client.get(f"{API}/alerts/?competitor=Zoetis", headers=service_headers)

    assert _ids(drag) == ["a3", "a4", "a5"]
    assert _ids(zoetis) == ["a1"]


def test_alerts_expose_a_competitor_field(client, alerts, service_headers):
    by_id = {a["id"]: a for a in client.get(f"{API}/alerts/", headers=service_headers).json()["data"]}

    assert by_id["a1"]["competitor"] == "ZOETIS CHILE S.A."
    assert by_id["a2"]["competitor"] == "AGROVET MARKET"
    assert by_id["a3"]["competitor"] == "DRAG PHARMA"
    assert by_id["a4"]["competitor"] == "Drag Pharma"


def test_counts_ignore_filters(client, alerts, service_headers):
    body = client.get(f"{API}/alerts/?priority=low", headers=service_headers).json()

    assert body["counts"] == {"total": 6, "critical": 2, "high": 1, "medium": 2, "low": 1}
    assert body["total"] == 1


def test_naive_mongo_datetimes_are_returned_as_utc(client, fake_db, service_headers):
    naive = (datetime.now(timezone.utc) + timedelta(days=1)).replace(tzinfo=None)
    fake_db.alerts.docs.append({**_alert("naive"), "created_at": naive, "expires_at": naive + timedelta(days=5)})

    created = client.get(f"{API}/alerts/naive", headers=service_headers).json()["data"]["created_at"]

    assert created.endswith("+00:00")
    assert datetime.fromisoformat(created) == naive.replace(tzinfo=timezone.utc)


def test_detail_returns_one_alert(client, alerts, service_headers):
    response = client.get(f"{API}/alerts/a2", headers=service_headers)

    assert response.status_code == 200
    assert response.json()["data"]["id"] == "a2"
    assert response.json()["data"]["competitor"] == "AGROVET MARKET"


def test_detail_of_unknown_alert_is_404(client, alerts, service_headers):
    assert client.get(f"{API}/alerts/no-existe", headers=service_headers).status_code == 404


def test_detail_requires_authentication(client, alerts):
    assert client.get(f"{API}/alerts/a1").status_code == 401
