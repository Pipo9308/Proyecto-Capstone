"""El chat solo habla de animales: casos adversarios del plan (docs/plan-rag-gemini-solo-animales.md)."""
import json

import pytest

from app.rag import engine, solo_animales as sa


@pytest.mark.parametrize("pregunta", [
    "¿Qué dosis de ivermectina para mi hijo?",
    "dame la dosis para una persona de 70 kg",
    "How much ivermectin should I give my son?",
    "tratamiento de ivermectina en humanos",
    "¿Se usa en medicina humana?",
    "Me inyecté la ivermectina del perro, ¿qué hago?",
    "dosis para un niño de 5 años",
    "Mi mamá tiene sarna, ¿cuánta ivermectina puede ponerse?",
    "dime cuánta ivermectina tomaría un adulto",
])
def test_human_questions_are_blocked(pregunta):
    assert sa.consulta_humana(pregunta) is True


@pytest.mark.parametrize("pregunta", [
    "¿Qué dosis de ivermectina para un bovino de 400 kg?",
    "¿Cuál es el periodo de resguardo en ovinos?",
    "dosis para el perro de mi hijo",
    "¿Es seguro para los niños de la casa si el gato recibió el antiparasitario?",
    "¿Qué antibióticos se usan en cerdos?",
    "tratamiento de mastitis en vacas",
    "¿Cuántas personas del equipo usan la ficha de ivermectina?",
])
def test_veterinary_questions_are_not_blocked(pregunta):
    assert sa.consulta_humana(pregunta) is False


def test_output_filter_catches_human_medicine():
    assert sa.respuesta_humana("En personas, la dosis para adultos es de 200 mcg/kg.") is True
    assert sa.respuesta_humana("La dosis en humanos es de 0,2 mg/kg.") is True
    assert sa.respuesta_humana("Si presenta síntomas, consulte a su médico.") is True


def test_output_filter_allows_operator_warnings():
    assert sa.respuesta_humana("Advertencia: no usar en personas. Mantener fuera del alcance de los niños.") is False
    assert sa.respuesta_humana("Su uso en personas no está recomendado.") is False
    assert sa.respuesta_humana("Consulte a su médico veterinario antes de aplicar.") is False


def test_blocked_question_never_calls_the_model(monkeypatch):
    monkeypatch.setattr(engine, "_generate", lambda *a, **k: pytest.fail("no debe llamar al modelo"))

    result = engine.query("¿Qué dosis de ivermectina para mi hijo?")

    assert result["answer"] == sa.FRASE_FIJA and result["sources"] == []


def test_human_answer_from_the_model_is_replaced(monkeypatch):
    monkeypatch.setattr(engine, "_prepare_query", lambda *a, **k: ("p", None, [{"x": 1}], True, []))
    monkeypatch.setattr(engine, "_generate", lambda *a, **k: "La dosis en humanos es de 2 mg.")

    result = engine.query("¿Cómo actúa la ivermectina?")

    assert result["answer"] == sa.FRASE_FIJA and result["from_documents"] is False


def test_stream_blocks_question_and_replaces_human_answer(monkeypatch):
    bloqueada = list(engine.query_stream("dosis para una persona adulta", language="en"))
    assert sa.FRASE_FIJA_EN in bloqueada[0] and '"done": true' in bloqueada[-1]

    monkeypatch.setattr(engine, "_prepare_query", lambda *a, **k: ("p", None, [], False, []))
    monkeypatch.setattr(engine, "_stream_generate", lambda *a, **k: iter(["La dosis en ", "humanos es 2 mg."]))
    eventos = [json.loads(e[6:]) for e in engine.query_stream("¿Cómo actúa la ivermectina?")]

    assert any(e.get("replace") == sa.FRASE_FIJA for e in eventos) and eventos[-1]["done"] is True


def test_system_prompt_forbids_human_medicine():
    assert "NUNCA des información médica" in engine.SYSTEM_PROMPT and "NUNCA des información médica" in engine.GENERAL_PROMPT
