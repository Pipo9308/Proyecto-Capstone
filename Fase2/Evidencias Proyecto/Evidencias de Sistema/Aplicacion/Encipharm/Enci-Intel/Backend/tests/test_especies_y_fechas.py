"""Filtro por especie del Consultor Vet y fechas de los agentes en UTC."""
from datetime import datetime

import pytest

from app.rag import engine
from app.rag.store import _es_de_la_especie

API = "/api/v1"


@pytest.mark.parametrize("enviada, interna", [
    ("Bovino", "Bovino"), ("Porcino", "Porcino"), ("Aviar", "Aviar"),  # lo que manda el frontend en espanol
    ("Canino", "Canino"), ("Felino", "Felino"), ("Equino", "Equino"),
    ("Bovine", "Bovino"), ("Poultry", "Aviar"),                        # ingles
])
def test_cada_especie_del_frontend_tiene_su_nombre_interno(enviada, interna):
    assert engine.SPECIES_MAP[enviada] == interna


def test_el_filtro_entiende_la_lista_de_especies_del_cargador():
    assert _es_de_la_especie({"species": ["Bovino", "Porcino"]}, "Bovino")
    assert not _es_de_la_especie({"species": ["Canino"]}, "Bovino")
    assert _es_de_la_especie({"species": []}, "Bovino")  # fragmento general: sirve para todas
    assert _es_de_la_especie({"species": "bovino"}, "Bovino")  # formato antiguo, texto suelto


def test_la_consulta_en_espanol_filtra_por_la_especie(monkeypatch):
    pedidos = []

    class Store:
        def search(self, emb, n, species, threshold):
            pedidos.append(species)
            return []

    monkeypatch.setattr(engine, "_store", Store())
    monkeypatch.setattr(engine, "_deepseek_client", object())
    monkeypatch.setattr(engine, "_embed", lambda textos, input_type="passage": [[0.0]])

    engine._prepare_query("dosis de ivermectina", "Bovino", None)
    engine._prepare_query("dosis de ivermectina", "Todas", None)

    assert pedidos == ["Bovino", None]


def test_las_fechas_de_los_agentes_salen_marcadas_como_utc(client, admin_headers, fake_db, monkeypatch):
    import app.api.agents as agents_api

    monkeypatch.setattr(agents_api._cache, "get", lambda key: None)
    monkeypatch.setattr(agents_api, "corriendo", lambda agent_id: False)
    sin_zona = datetime(2026, 11, 17, 1, 11, 35)  # asi las devuelve Firestore (UTC)
    fake_db.agents.docs.append({"_id": "agente_sag", "name": "Agente SAG", "last_run": sin_zona})
    fake_db.agent_runs.docs.append({"_id": "r1", "agent_id": "agente_sag", "status": "success",
                                    "started_at": sin_zona, "ended_at": sin_zona})

    agente = client.get(f"{API}/agents/", headers=admin_headers).json()["data"][0]
    corrida = client.get(f"{API}/agents/agente_sag/runs", headers=admin_headers).json()["data"][0]
    detalle = client.get(f"{API}/agents/agente_sag", headers=admin_headers).json()["data"]

    assert agente["last_run"] == detalle["last_run"] == "2026-11-17T01:11:35+00:00"
    assert corrida["started_at"].endswith("+00:00") and corrida["ended_at"].endswith("+00:00")
