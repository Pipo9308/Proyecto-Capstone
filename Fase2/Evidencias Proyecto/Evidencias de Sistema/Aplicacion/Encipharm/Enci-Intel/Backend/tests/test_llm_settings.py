from types import SimpleNamespace

import pytest

from app import llm_settings

API = "/api/v1/admin/llm"
BODY = {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "model": "gemini-2.5-flash",
        "competencia_model": "gemini-2.5-pro", "api_key": "AIza-secreta-1234"}


@pytest.fixture(autouse=True)
def _limpio(monkeypatch):
    monkeypatch.setattr(llm_settings, "_saved", {})
    monkeypatch.setattr(llm_settings, "_rag", {})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")


def test_only_admin_can_read_or_change(client, user_headers):
    assert client.get(f"{API}/", headers=user_headers).status_code == 403
    assert client.put(f"{API}/", json=BODY, headers=user_headers).status_code == 403


def test_defaults_come_from_environment(client, admin_headers):
    data = client.get(f"{API}/", headers=admin_headers).json()["data"]

    assert data["source"] == "entorno" and data["model"] == "deepseek-chat" and data["api_key_set"] is False


def test_save_changes_effective_model_and_hides_the_key(client, fake_db, admin_headers):
    response = client.put(f"{API}/", json=BODY, headers=admin_headers)

    data = response.json()["data"]
    assert response.status_code == 200 and data["model"] == "gemini-2.5-flash" and data["source"] == "guardado"
    assert data["api_key_hint"] == "1234" and "AIza" not in response.text
    assert llm_settings.effective()["model"] == "gemini-2.5-flash"
    assert fake_db.app_settings.docs[0]["_id"] == "llm"


def test_empty_key_keeps_the_saved_one(client, admin_headers):
    client.put(f"{API}/", json=BODY, headers=admin_headers)
    client.put(f"{API}/", json={**BODY, "model": "gemini-2.5-pro", "api_key": ""}, headers=admin_headers)

    assert llm_settings.effective()["api_key"] == "AIza-secreta-1234"
    assert llm_settings.effective()["model"] == "gemini-2.5-pro"


def test_new_provider_requires_a_key(client, admin_headers):
    response = client.put(f"{API}/", json={**BODY, "api_key": ""}, headers=admin_headers)

    assert response.status_code == 400


def test_provider_url_must_be_https(client, admin_headers):
    assert client.put(f"{API}/", json={**BODY, "base_url": "http://x.test"}, headers=admin_headers).status_code == 400


def test_runtime_is_for_services_only(client, admin_headers, service_headers):
    client.put(f"{API}/", json=BODY, headers=admin_headers)

    assert client.get(f"{API}/runtime", headers=admin_headers).status_code == 403
    runtime = client.get(f"{API}/runtime", headers=service_headers).json()
    assert runtime["api_key"] == "AIza-secreta-1234" and runtime["competencia_model"] == "gemini-2.5-pro"


def test_per_agent_models_are_saved_and_exposed(client, admin_headers):
    response = client.put(f"{API}/", json={**BODY, "competidores_model": "gemini-2.5-pro", "sag_model": "gemini-2.5-flash"},
                          headers=admin_headers)

    data = response.json()["data"]
    assert data["competidores_model"] == "gemini-2.5-pro" and data["sag_model"] == "gemini-2.5-flash"
    assert llm_settings.effective()["model"] == "gemini-2.5-flash"  # el modelo general no cambia


ANTHROPIC = {**BODY, "agentes_proveedor": "anthropic", "anthropic_api_key": "sk-ant-secreta-9876",
             "competidores_model": "claude-opus-5-5", "sag_model": "claude-haiku-5-5"}


def test_anthropic_for_agents_requires_its_own_key(client, admin_headers):
    response = client.put(f"{API}/", json={**ANTHROPIC, "anthropic_api_key": ""}, headers=admin_headers)

    assert response.status_code == 400


def test_anthropic_key_is_encrypted_hidden_and_not_sent_to_ventas(client, fake_db, admin_headers, service_headers):
    response = client.put(f"{API}/", json=ANTHROPIC, headers=admin_headers)

    data = response.json()["data"]
    assert data["agentes_proveedor"] == "anthropic" and data["anthropic_key_hint"] == "9876"
    assert "sk-ant" not in response.text
    assert fake_db.app_settings.docs[0]["anthropic_api_key"].startswith("enc:")
    assert llm_settings.effective()["model"] == "gemini-2.5-flash"  # los chats siguen con el proveedor general
    assert "anthropic_api_key" not in client.get(f"{API}/runtime", headers=service_headers).json()


def test_empty_anthropic_key_keeps_the_saved_one(client, admin_headers):
    client.put(f"{API}/", json=ANTHROPIC, headers=admin_headers)
    client.put(f"{API}/", json={**ANTHROPIC, "anthropic_api_key": ""}, headers=admin_headers)

    assert llm_settings.saved()["anthropic_api_key"] == "sk-ant-secreta-9876"


def _anthropic_falso(monkeypatch, error=None):
    import anthropic

    class Modelos:
        def list(self):
            async def pagina():
                if error:
                    raise error
                yield SimpleNamespace(id="claude-opus-5-5", display_name="Claude Opus 5.5")
                yield SimpleNamespace(id="claude-haiku-5-5", display_name="Claude Haiku 5.5")
            return pagina()

    vistos = []
    monkeypatch.setattr(anthropic, "AsyncAnthropic", lambda **kw: vistos.append(kw) or SimpleNamespace(models=Modelos()))
    return vistos


def test_connecting_to_anthropic_lists_its_models(client, admin_headers, user_headers, monkeypatch):
    vistos = _anthropic_falso(monkeypatch)

    assert client.post(f"{API}/anthropic/modelos", json={"api_key": "sk-x"}, headers=user_headers).status_code == 403
    data = client.post(f"{API}/anthropic/modelos", json={"api_key": "sk-x"}, headers=admin_headers).json()["data"]

    assert data["ok"] is True and [m["id"] for m in data["modelos"]] == ["claude-opus-5-5", "claude-haiku-5-5"]
    assert vistos[0]["api_key"] == "sk-x"


def test_listing_models_uses_the_saved_key_and_reports_errors(client, admin_headers, monkeypatch):
    assert client.post(f"{API}/anthropic/modelos", json={}, headers=admin_headers).status_code == 400  # sin key

    client.put(f"{API}/", json=ANTHROPIC, headers=admin_headers)
    vistos = _anthropic_falso(monkeypatch, error=RuntimeError("caido"))
    data = client.post(f"{API}/anthropic/modelos", json={}, headers=admin_headers).json()["data"]

    assert vistos[0]["api_key"] == "sk-ant-secreta-9876" and data["ok"] is False and "caido" in data["detail"]


RAG = {"instrucciones": "Eres un consultor veterinario breve y preciso.", "temperatura": 0.5, "max_tokens": 600,
       "documentos": 3, "umbral": 0.6}


def test_rag_shows_defaults_and_fixed_rules(client, admin_headers, user_headers):
    assert client.get(f"{API}/rag", headers=user_headers).status_code == 403
    data = client.get(f"{API}/rag", headers=admin_headers).json()["data"]

    assert data["source"] == "por_defecto" and data["vigente"] == data["por_defecto"]
    assert "REGLAS ABSOLUTAS" in data["reglas"]


def test_saving_rag_changes_engine_but_keeps_the_rules(client, fake_db, admin_headers):
    from app.rag import engine

    data = client.put(f"{API}/rag", json=RAG, headers=admin_headers).json()["data"]

    assert data["source"] == "guardado" and data["vigente"]["documentos"] == 3
    assert engine.rag_config()["temperatura"] == 0.5 and engine.rag_config()["max_tokens"] == 600
    prompt = engine._system_prompt()
    assert prompt.startswith("Eres un consultor veterinario breve") and "NUNCA des información médica" in prompt
    assert any(d["_id"] == "rag" for d in fake_db.app_settings.docs)


def test_rag_values_are_validated(client, admin_headers):
    assert client.put(f"{API}/rag", json={**RAG, "temperatura": 2}, headers=admin_headers).status_code == 422
    assert client.put(f"{API}/rag", json={**RAG, "documentos": 0}, headers=admin_headers).status_code == 422
    assert client.put(f"{API}/rag", json={**RAG, "instrucciones": "corto"}, headers=admin_headers).status_code == 422


GENERAL_CLAUDE = {"proveedor": "anthropic", "base_url": "", "model": "claude-sonnet-5-5",
                  "competencia_model": "claude-haiku-5-5", "anthropic_api_key": "sk-ant-general-5555"}


def test_anthropic_as_general_provider_needs_no_url_but_its_key(client, admin_headers):
    assert client.put(f"{API}/", json={**GENERAL_CLAUDE, "anthropic_api_key": ""}, headers=admin_headers).status_code == 400

    data = client.put(f"{API}/", json=GENERAL_CLAUDE, headers=admin_headers).json()["data"]

    assert data["proveedor"] == "anthropic" and data["model"] == "claude-sonnet-5-5"
    assert llm_settings.es_anthropic(llm_settings.effective())


def test_ventas_gets_the_anthropic_key_only_when_chats_use_claude(client, admin_headers, service_headers):
    client.put(f"{API}/", json=GENERAL_CLAUDE, headers=admin_headers)

    runtime = client.get(f"{API}/runtime", headers=service_headers).json()

    assert runtime["proveedor"] == "anthropic" and runtime["anthropic_api_key"] == "sk-ant-general-5555"


def test_rag_answers_with_claude_when_it_is_the_general_provider(client, admin_headers, monkeypatch):
    import anthropic

    from app.rag import engine

    client.put(f"{API}/", json=GENERAL_CLAUDE, headers=admin_headers)
    llamadas = []

    class Messages:
        def create(self, **kwargs):
            llamadas.append(kwargs)
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=" Respuesta ")])

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: SimpleNamespace(messages=Messages()))
    monkeypatch.setattr(engine, "_gen_cache", {})
    historial = [{"role": "assistant", "content": "hola"}, {"role": "user", "content": "previa"},
                 {"role": "assistant", "content": "resp"}]

    assert engine._generate("PREGUNTA: x", history=historial) == "Respuesta"
    pedido = llamadas[0]
    assert pedido["model"] == "claude-sonnet-5-5" and "temperature" not in pedido
    assert "REGLAS ABSOLUTAS" in pedido["system"]
    assert [m["role"] for m in pedido["messages"]] == ["user", "assistant", "user"]  # empieza por user


def test_rag_stream_with_claude_replaces_a_refusal(client, admin_headers, monkeypatch):
    import anthropic

    from app.rag import engine

    client.put(f"{API}/", json=GENERAL_CLAUDE, headers=admin_headers)

    class Stream:
        text_stream = iter([])

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            return SimpleNamespace(stop_reason="refusal")

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: SimpleNamespace(messages=SimpleNamespace(stream=lambda **k: Stream())))
    monkeypatch.setattr(engine, "_gen_cache", {})

    assert list(engine._stream_generate("x")) == [engine.CLAUDE_RECHAZO]


def test_consultor_answers_with_claude_even_without_an_embeddings_key(client, admin_headers, monkeypatch):
    import anthropic

    from app.rag import engine

    client.put(f"{API}/", json=GENERAL_CLAUDE, headers=admin_headers)
    llamadas = []

    class Messages:
        def create(self, **kwargs):
            llamadas.append(kwargs)
            return SimpleNamespace(stop_reason="end_turn", content=[
                SimpleNamespace(type="text", text="Esta respuesta se basa en conocimiento general. Hola.")])

    monkeypatch.setattr(anthropic, "Anthropic", lambda **kw: SimpleNamespace(messages=Messages()))
    monkeypatch.setattr(engine, "_gen_cache", {})
    monkeypatch.setattr(engine, "_store", None)  # sin DEEPSEEK_API_KEY el motor no carga documentos
    monkeypatch.setattr(engine, "_deepseek_client", None)

    resultado = engine.query("hola, ¿qué vacunas usa un bovino?")

    assert resultado["answer"].endswith("Hola.") and resultado["sources"] == [] and resultado["from_documents"] is False
    assert llamadas[0]["system"] == engine.GENERAL_PROMPT
