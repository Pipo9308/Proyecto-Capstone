"""El cliente LLM real, probado contra un servidor local compatible con OpenAI (sin API key):
comprueba el formato de la peticion con herramientas y la lectura de tool_calls y del uso."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.services.competencia_llm import OpenAICompatibleClient, build_llm_client


class _Server:
    def __init__(self, responses):
        self.responses = list(responses)  # (status, body)
        self.requests = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                outer.requests.append({"path": self.path, "auth": self.headers.get("Authorization"),
                                       "body": json.loads(self.rfile.read(length) or b"{}")})
                status, body = outer.responses.pop(0)
                payload = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.httpd.server_port}/v1"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()


def _completion(message, prompt=11, completion=7):
    return {
        "id": "x", "object": "chat.completion", "created": 0, "model": "m",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", **message}}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion},
    }


TOOLS = [{"type": "function", "function": {"name": "buscar_alertas", "description": "d", "parameters": {"type": "object", "properties": {}}}}]


@pytest.mark.anyio
async def test_sends_tools_and_parses_tool_calls_and_usage():
    tool_call = {"id": "call_1", "type": "function", "function": {"name": "buscar_alertas", "arguments": '{"competidor": "zoetis"}'}}
    with _Server([(200, _completion({"content": None, "tool_calls": [tool_call]}))]) as server:
        client = OpenAICompatibleClient("clave", server.url, "modelo-x", 500)

        reply = await client.complete([{"role": "user", "content": "hola"}], TOOLS)

    sent = server.requests[0]
    assert sent["path"] == "/v1/chat/completions" and sent["auth"] == "Bearer clave"
    assert sent["body"]["model"] == "modelo-x" and sent["body"]["max_tokens"] == 500
    assert sent["body"]["tools"] == TOOLS and sent["body"]["tool_choice"] == "auto"
    assert reply.tool_calls[0].name == "buscar_alertas" and reply.tool_calls[0].arguments == {"competidor": "zoetis"}
    assert reply.tool_calls[0].id == "call_1"
    assert (reply.tokens_in, reply.tokens_out) == (11, 7)


@pytest.mark.anyio
async def test_plain_answer_without_tools_omits_the_tools_fields():
    with _Server([(200, _completion({"content": "Respuesta final"}))]) as server:
        reply = await OpenAICompatibleClient("k", server.url, "m", 100).complete([{"role": "user", "content": "x"}], None)

    assert reply.content == "Respuesta final" and reply.tool_calls == []
    assert "tools" not in server.requests[0]["body"] and "tool_choice" not in server.requests[0]["body"]


@pytest.mark.anyio
async def test_invalid_tool_arguments_do_not_crash():
    broken = {"id": "c", "type": "function", "function": {"name": "buscar_alertas", "arguments": "{no es json"}}
    with _Server([(200, _completion({"content": "", "tool_calls": [broken]}))]) as server:
        reply = await OpenAICompatibleClient("k", server.url, "m", 100).complete([{"role": "user", "content": "x"}], TOOLS)

    assert reply.tool_calls[0].arguments == {"_error": "argumentos invalidos"}


@pytest.mark.anyio
@pytest.mark.parametrize("status, code", [(401, "COMPETENCIA_LLM_AUTH_FAILED"), (429, "COMPETENCIA_LLM_RATE_LIMITED")])
async def test_provider_errors_become_503_with_a_code(status, code):
    with _Server([(status, {"error": {"message": "x", "type": "x"}})] * 3) as server:
        client = OpenAICompatibleClient("k", server.url, "m", 100)

        with pytest.raises(HTTPException) as error:
            await client.complete([{"role": "user", "content": "x"}], None)

    assert error.value.status_code == 503 and error.value.detail["codigo"] == code


def test_build_client_requires_a_provider_key_and_uses_the_competition_model():
    base = get_settings()

    with pytest.raises(HTTPException) as error:
        build_llm_client(base.model_copy(update={"DEEPSEEK_API_KEY": None}))
    assert error.value.detail["codigo"] == "COMPETENCIA_LLM_NOT_CONFIGURED"

    configured = build_llm_client(base.model_copy(update={
        "DEEPSEEK_API_KEY": "k", "DEEPSEEK_MODEL": "modelo-rag", "COMPETENCIA_MODEL": "modelo-competencia",
    }))
    assert configured._model == "modelo-competencia"

    fallback = build_llm_client(base.model_copy(update={"DEEPSEEK_API_KEY": "k", "DEEPSEEK_MODEL": "modelo-rag", "COMPETENCIA_MODEL": None}))
    assert fallback._model == "modelo-rag"


# --- Claude (proveedor "anthropic"): el SDK oficial contra el mismo servidor local ---

def _claude_msg(content, stop="end_turn", entrada=10, salida=5):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-x", "content": content,
            "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": entrada, "output_tokens": salida}}


@pytest.mark.anyio
async def test_claude_tool_round_trip_keeps_thinking_and_sends_tool_results(monkeypatch):
    from app.services.competencia_llm import AnthropicClient

    primera = _claude_msg([
        {"type": "thinking", "thinking": "", "signature": "firma-1"},
        {"type": "tool_use", "id": "tu_1", "name": "buscar_alertas", "input": {"competidor": "zoetis"}},
    ], stop="tool_use")
    with _Server([(200, primera), (200, _claude_msg([{"type": "text", "text": "Listo"}]))]) as server:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", server.url.removesuffix("/v1"))
        client = AnthropicClient("clave-ant", "claude-x", 900)
        mensajes = [{"role": "system", "content": "sistema"}, {"role": "assistant", "content": "saludo previo"},
                    {"role": "user", "content": "hola"}]

        reply = await client.complete(mensajes, TOOLS)
        mensajes.append({"role": "assistant", "content": None, "tool_calls": [], "_claude": reply.raw})
        mensajes.append({"role": "tool", "tool_call_id": "tu_1", "content": '{"items": []}'})
        mensajes.append({"role": "user", "content": "Responde ahora"})
        final = await client.complete(mensajes, None)

    assert reply.tool_calls[0].id == "tu_1" and reply.tool_calls[0].arguments == {"competidor": "zoetis"}
    assert (reply.tokens_in, reply.tokens_out) == (10, 5) and final.content == "Listo"
    pedido1, pedido2 = server.requests[0]["body"], server.requests[1]["body"]
    assert server.requests[0]["path"] == "/v1/messages" and pedido1["system"] == "sistema"
    assert pedido1["max_tokens"] >= 16000 and "temperature" not in pedido1
    assert pedido1["tools"] == [{"name": "buscar_alertas", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    assert [m["role"] for m in pedido1["messages"]] == ["user"]  # el saludo del asistente al inicio se descarta
    assert pedido2["tool_choice"] == {"type": "none"} and pedido2["tools"] == pedido1["tools"]
    assert pedido2["messages"][1]["content"][0] == {"type": "thinking", "thinking": "", "signature": "firma-1"}
    assert [b["type"] for b in pedido2["messages"][2]["content"]] == ["tool_result", "text"]


@pytest.mark.anyio
async def test_claude_refusal_and_auth_errors(monkeypatch):
    from app.services.competencia_llm import CLAUDE_RECHAZO, AnthropicClient

    with _Server([(200, _claude_msg([], stop="refusal")), (401, {"type": "error", "error": {"type": "authentication_error", "message": "x"}})]) as server:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", server.url.removesuffix("/v1"))
        client = AnthropicClient("k", "claude-x", 900)

        assert (await client.complete([{"role": "user", "content": "x"}], None)).content == CLAUDE_RECHAZO
        with pytest.raises(HTTPException) as error:
            await client.complete([{"role": "user", "content": "x"}], None)

    assert error.value.detail["codigo"] == "COMPETENCIA_LLM_AUTH_FAILED"


def test_build_client_uses_claude_when_the_provider_is_anthropic():
    from app.services.competencia_llm import AnthropicClient

    base = get_settings().model_copy(update={"LLM_PROVIDER": "anthropic", "DEEPSEEK_MODEL": "claude-a", "COMPETENCIA_MODEL": None})

    with pytest.raises(HTTPException) as error:
        build_llm_client(base.model_copy(update={"ANTHROPIC_API_KEY": None}))
    assert error.value.detail["codigo"] == "COMPETENCIA_LLM_NOT_CONFIGURED"

    cliente = build_llm_client(base.model_copy(update={"ANTHROPIC_API_KEY": "k"}))
    assert isinstance(cliente, AnthropicClient) and cliente._model == "claude-a"


@pytest.mark.anyio
async def test_rag_assistant_answers_with_claude(monkeypatch):
    from app.services import llm_service

    async def overrides():
        return {"LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "k", "DEEPSEEK_MODEL": "claude-rag"}

    monkeypatch.setattr(llm_service, "llm_overrides", overrides)
    with _Server([(200, _claude_msg([{"type": "text", "text": "Hola"}], entrada=7, salida=3))]) as server:
        monkeypatch.setenv("ANTHROPIC_BASE_URL", server.url.removesuffix("/v1"))
        resultado = await llm_service.call_deepseek("sistema", "pregunta", max_tokens=50)

    assert resultado == {"texto": "Hola", "tokens": 10, "modelo": "claude-rag"}
    pedido = server.requests[0]["body"]
    assert pedido["system"] == "sistema" and pedido["model"] == "claude-rag" and "temperature" not in pedido
