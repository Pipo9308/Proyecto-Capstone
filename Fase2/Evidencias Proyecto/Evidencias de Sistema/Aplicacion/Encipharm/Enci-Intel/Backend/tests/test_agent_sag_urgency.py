"""Urgencia diferenciada del agente SAG por categoria terapeutica.

Antes de este cambio, todo "nuevo registro" tenia urgencia fija 75 y toda
"cancelacion" urgencia fija 90, sin importar si el producto era un
antiparasitario cualquiera o un nuevo antibiotico/vacuna de un competidor.
"""
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1] / "agents" / "agent-sag"
sys.path.insert(0, str(AGENT_DIR))

from detector import _resolve_urgency, _urgency_to_priority  # noqa: E402


class TestResolveUrgency:
    def test_categoria_estrategica_antimicrobianos_nuevo_registro(self):
        assert _resolve_urgency("ANTIMICROBIANOS", es_cancelacion=False) == 80

    def test_categoria_estrategica_inmunologico_cancelacion(self):
        assert _resolve_urgency("INMUNOLOGICO", es_cancelacion=True) == 90

    def test_alto_volumen_antiparasitario_nuevo_registro(self):
        assert _resolve_urgency("ANTIPARASITARIO", es_cancelacion=False) == 65

    def test_alto_volumen_antiparasitario_cancelacion(self):
        assert _resolve_urgency("ANTIPARASITARIO", es_cancelacion=True) == 75

    def test_categoria_generica_nuevo_registro(self):
        assert _resolve_urgency("MISCELANEOS", es_cancelacion=False) == 55

    def test_categoria_generica_cancelacion(self):
        assert _resolve_urgency("HORMONA", es_cancelacion=True) == 65

    def test_categoria_vacia_o_ausente_cae_en_generica(self):
        assert _resolve_urgency(None, es_cancelacion=False) == 55
        assert _resolve_urgency("", es_cancelacion=True) == 65

    def test_es_insensible_a_mayusculas_y_espacios(self):
        assert _resolve_urgency("  antimicrobianos  ", es_cancelacion=False) == 80
        assert _resolve_urgency("Inmunologico", es_cancelacion=True) == 90

    def test_categoria_estrategica_siempre_prioridad_alta_o_critica(self):
        for es_cancelacion in (True, False):
            urgencia = _resolve_urgency("INMUNOLOGICO", es_cancelacion)
            assert _urgency_to_priority(urgencia) in ("critical", "high")

    def test_cancelacion_siempre_es_mas_o_igual_urgente_que_nuevo_en_misma_categoria(self):
        for categoria in ["ANTIMICROBIANOS", "INMUNOLOGICO", "ANTIPARASITARIO", "MISCELANEOS", "HORMONA"]:
            nuevo = _resolve_urgency(categoria, es_cancelacion=False)
            cancelacion = _resolve_urgency(categoria, es_cancelacion=True)
            assert cancelacion >= nuevo

    def test_categoria_estrategica_es_mas_urgente_que_alto_volumen(self):
        assert _resolve_urgency("ANTIMICROBIANOS", False) > _resolve_urgency("ANTIPARASITARIO", False)
        assert _resolve_urgency("INMUNOLOGICO", True) > _resolve_urgency("ANTIPARASITARIO", True)
