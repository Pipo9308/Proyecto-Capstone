import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

AGENT_DIR = Path(__file__).resolve().parents[1] / "agents" / "agent-sag"
sys.path.insert(0, str(AGENT_DIR))

import enriquecedor_sag  # noqa: E402
from detector import BONO_SOLAPAMIENTO, _con_analisis  # noqa: E402

CFG = {"api_key": "k", "base_url": "https://x.test", "model": "m"}


class _Productos:
    def find(self):
        return SimpleNamespace(to_list=lambda length=None: [{"nombre": "Oxivet 200 LA", "especie": "Bovino"}, {"nombre": "Ivermectina Plus"}, {"especie": "sin nombre"}])


def _modelo_falso(monkeypatch, contenido=None, error=None):
    def falso(cfg, sistema, usuario, max_tokens=1500):
        if error:
            raise error
        return json.loads(contenido)

    monkeypatch.setattr(enriquecedor_sag, "pedir_json", falso)


def _datos():
    df = pd.DataFrame([
        {"Registro": "10", "Nombre comercial": "Oxi X", "Principios Activos": "oxitetraciclina", "Clasificación": "ANTIMICROBIANOS"},
        {"Registro": "11", "Nombre comercial": "Otro", "Principios Activos": "vitamina", "Clasificación": "MISCELANEOS"},
    ])
    previos = {"12": {"Nombre comercial": "Viejo", "Clasificación": "HORMONA"}}
    return SimpleNamespace(products=_Productos()), df, previos


def test_analysis_keeps_only_real_catalog_names(monkeypatch):
    items = {"items": [
        {"i": 0, "resumen": "Antibiotico bovino.", "solapa_con": ["oxivet 200 la", "Producto Inventado"]},
        {"i": 1, "resumen": "Vitamina.", "solapa_con": []},
        {"i": 2, "resumen": "Hormona descontinuada.", "solapa_con": "no es lista"},
    ]}
    _modelo_falso(monkeypatch, json.dumps(items))
    db, df, previos = _datos()

    resultado = enriquecedor_sag.analizar(db, df, {"10", "11"}, {"12"}, previos, CFG)

    assert resultado["10"] == {"resumen": "Antibiotico bovino.", "solapa_con": ["Oxivet 200 LA"]}
    assert resultado["11"]["solapa_con"] == [] and resultado["12"]["solapa_con"] == []


def test_model_failure_gives_no_analysis(monkeypatch):
    _modelo_falso(monkeypatch, error=RuntimeError("caido"))
    db, df, previos = _datos()

    assert enriquecedor_sag.analizar(db, df, {"10"}, set(), previos, CFG) == {}


def test_overlap_raises_urgency_and_adds_summary():
    extra = {"resumen": "Antibiotico bovino.", "solapa_con": ["Oxivet 200 LA"]}

    urgency, description, data = _con_analisis(80, "Competidor: X", {"Registro": "10"}, extra)

    assert urgency == 80 + BONO_SOLAPAMIENTO and description.endswith("Antibiotico bovino.")
    assert data["solapa_con"] == ["Oxivet 200 LA"] and data["Registro"] == "10"


def test_urgency_is_capped_and_no_overlap_keeps_it():
    assert _con_analisis(95, "d", {}, {"resumen": "r", "solapa_con": ["A"]})[0] == 100
    assert _con_analisis(65, "d", {}, {"resumen": "r", "solapa_con": []})[0] == 65
    assert _con_analisis(65, "d", {"a": 1}, None) == (65, "d", {"a": 1})
