"""El agente SAG escribe y lee en Firestore a traves de la capa sincrona (emulador; sin emulador se omite)."""
import importlib.util
import os
import sys
from pathlib import Path

import pandas as pd
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("FIRESTORE_EMULATOR_HOST"), reason="sin emulador de Firestore")

AGENT_DIR = Path(__file__).resolve().parents[1] / "agents" / "agent-sag"


def _load(name):
    sys.path.insert(0, str(AGENT_DIR))
    try:
        spec = importlib.util.spec_from_file_location(f"sag_{name}", AGENT_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(AGENT_DIR))


def test_el_agente_sag_sincroniza_productos_y_alertas_en_firestore():
    from app.firestore_db import SyncDatabase

    detector = _load("detector")
    detector.COLECCION = f"sag_test_{os.urandom(4).hex()}"
    db = SyncDatabase("enci-test")
    df = pd.DataFrame([
        {"Registro": "1001", "Nombre comercial": "Draxxin", "Empresa Fabricante": "ZOETIS", "Importador o Registrante": "ZOETIS CHILE", "Clasificación": "ANTIMICROBIANOS"},
        {"Registro": "1002", "Nombre comercial": "Otro", "Empresa Fabricante": "AGROVET", "Importador o Registrante": "AGROVET", "Clasificación": "ANTIPARASITARIO"},
    ])

    detector.sincronizar_productos(db, df, cancelados=set())
    previos = detector.cargar_registros_previos(db)
    nuevos, cancelados = detector.detectar_cambios(df.iloc[:1], previos)
    detector.sincronizar_productos(db, df.iloc[:1], cancelados={"1002"})

    assert set(previos) == {"1001", "1002"}
    assert nuevos == set() and cancelados == {"1002"}
    estado = {d["_id"]: d["status"] for d in db[detector.COLECCION].find()}
    assert estado == {"1001": "activo", "1002": "cancelado"}
    assert db[detector.COLECCION].find_one({"_id": "1001"})["Nombre comercial"] == "Draxxin"  # campos con espacios y tildes
