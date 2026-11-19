import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents" / "agent-competidores"))
import enriquecedor  # noqa: E402

CFG = {"api_key": "k", "base_url": "https://x.test", "model": "m"}


def _cliente_falso(monkeypatch, contenido=None, error=None):
    class Completions:
        def create(self, **kwargs):
            if error:
                raise error
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=contenido))])

    import openai
    monkeypatch.setattr(openai, "OpenAI", lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=Completions())))


def _noticias():
    return [
        {"id": "a", "empresa": "ZOETIS", "origen": "prensa", "titulo": "Zoetis lanza vacuna", "resumen": ""},
        {"id": "b", "empresa": "AGROVET", "origen": "prensa", "titulo": "Agrovet de Leon", "resumen": ""},
        {"id": "c", "empresa": "DRAG PHARMA", "titulo": "Jornada tecnica", "resumen": "texto"},
    ]


def test_model_output_is_applied_and_clamped(monkeypatch):
    items = [
        {"i": 0, "relevante": True, "tipo": "lanzamiento", "urgencia": 250, "resumen": "Nueva vacuna."},
        {"i": 1, "relevante": False, "tipo": "INVENTADO", "urgencia": "alta", "resumen": "x"},
        {"i": 2, "relevante": False, "tipo": "EVENTO", "urgencia": 30, "resumen": "Evento."},
    ]
    _cliente_falso(monkeypatch, "```json\n" + json.dumps({"items": items}) + "\n```")
    noticias = _noticias()

    enriquecedor.enriquecer(noticias, CFG)

    assert (noticias[0]["tipo"], noticias[0]["urgencia"], noticias[0]["relevante"]) == ("LANZAMIENTO", 100, True)
    assert (noticias[1]["tipo"], noticias[1]["urgencia"], noticias[1]["relevante"]) == ("OTRO", 55, False)
    assert noticias[2]["relevante"] is True  # sitio propio del competidor: el modelo no lo descarta


def test_model_failure_leaves_news_untouched(monkeypatch):
    _cliente_falso(monkeypatch, error=RuntimeError("caido"))
    noticias = _noticias()

    enriquecedor.enriquecer(noticias, CFG)

    assert all("relevante" not in n and "urgencia" not in n for n in noticias)


def test_invalid_json_leaves_news_untouched(monkeypatch):
    _cliente_falso(monkeypatch, "no es json")
    noticias = _noticias()

    enriquecedor.enriquecer(noticias, CFG)

    assert all("tipo" not in n for n in noticias)


def test_config_requires_an_api_key(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    sin_nada = SimpleNamespace(app_settings=SimpleNamespace(find_one=lambda q: None))
    guardada = SimpleNamespace(app_settings=SimpleNamespace(find_one=lambda q: {"api_key": "k2", "model": "gemini"}))

    assert enriquecedor.cargar_config(sin_nada) is None
    assert enriquecedor.cargar_config(guardada)["model"] == "gemini"


def test_each_agent_uses_its_own_model_when_set(monkeypatch):
    from app import llm_agentes

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    doc = {"model": "general", "competidores_model": "modelo-comp"}
    db = SimpleNamespace(app_settings=SimpleNamespace(find_one=lambda q: doc))

    assert llm_agentes.cargar_config(db, "competidores")["model"] == "modelo-comp"
    assert llm_agentes.cargar_config(db, "sag")["model"] == "general"  # sin modelo propio: el general
    assert llm_agentes.cargar_config(db)["model"] == "general"


def test_agents_use_anthropic_with_its_own_key_when_chosen(monkeypatch):
    from app import llm_agentes

    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    doc = {"model": "general", "agentes_proveedor": "anthropic", "anthropic_api_key": "sk-ant",
           "sag_model": "claude-haiku-5-5"}
    db = SimpleNamespace(app_settings=SimpleNamespace(find_one=lambda q: doc))

    assert llm_agentes.cargar_config(db, "sag") == {"proveedor": "anthropic", "api_key": "sk-ant", "model": "claude-haiku-5-5"}
    assert llm_agentes.cargar_config(db, "competidores")["model"] == llm_agentes.ANTHROPIC_MODELO  # sin modelo elegido
    assert llm_agentes.cargar_config(SimpleNamespace(app_settings=SimpleNamespace(
        find_one=lambda q: {**doc, "anthropic_api_key": ""}))) is None  # sin key de Anthropic no corre


def test_pedir_json_calls_claude_and_reads_text_blocks(monkeypatch):
    import anthropic

    from app import llm_agentes

    llamadas = []

    class Messages:
        def create(self, **kwargs):
            llamadas.append(kwargs)
            return SimpleNamespace(stop_reason="end_turn", content=[
                SimpleNamespace(type="thinking", thinking=""),
                SimpleNamespace(type="text", text='```json\n{"items": []}\n```'),
            ])

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: SimpleNamespace(messages=Messages()))
    cfg = {"proveedor": "anthropic", "api_key": "sk-ant", "model": "claude-opus-5-5"}

    assert llm_agentes.pedir_json(cfg, "sistema", "usuario") == {"items": []}
    assert llamadas[0]["system"] == "sistema" and llamadas[0]["model"] == "claude-opus-5-5"
    assert "temperature" not in llamadas[0]  # los modelos actuales de Claude rechazan temperature


def test_claude_refusal_raises(monkeypatch):
    import anthropic

    from app import llm_agentes

    respuesta = SimpleNamespace(stop_reason="refusal", content=[])
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda **kw: SimpleNamespace(messages=SimpleNamespace(create=lambda **k: respuesta)))

    with pytest.raises(RuntimeError):
        llm_agentes.pedir_json({"proveedor": "anthropic", "api_key": "k", "model": "m"}, "s", "u")


def test_agents_follow_a_general_anthropic_provider(monkeypatch):
    from app import llm_agentes

    doc = {"proveedor": "anthropic", "model": "claude-sonnet-5-5", "anthropic_api_key": "sk-ant", "sag_model": "claude-haiku-5-5"}
    db = SimpleNamespace(app_settings=SimpleNamespace(find_one=lambda q: doc))

    assert llm_agentes.cargar_config(db, "sag")["model"] == "claude-haiku-5-5"
    assert llm_agentes.cargar_config(db, "competidores") == {"proveedor": "anthropic", "api_key": "sk-ant",
                                                              "model": "claude-sonnet-5-5"}


def test_describir_ia_dice_que_modelo_usaria_el_agente_sin_mostrar_la_key():
    from app.llm_agentes import describir_ia

    assert describir_ia(None) == "sin configurar"
    assert describir_ia({"proveedor": "anthropic", "api_key": "sk-ant-secreta", "model": "claude-sonnet-5-5"}) == \
        "Anthropic · claude-sonnet-5-5"
    assert describir_ia({"api_key": "k", "base_url": "https://x", "model": "deepseek-chat"}) == "Compatible OpenAI · deepseek-chat"
