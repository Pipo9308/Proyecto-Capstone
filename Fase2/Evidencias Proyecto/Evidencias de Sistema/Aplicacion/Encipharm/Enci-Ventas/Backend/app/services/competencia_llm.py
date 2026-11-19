"""Cliente LLM del chat de competencia: una interfaz minima para poder cambiar de
proveedor o de modelo por variables de entorno y probar el flujo con un cliente falso."""
import json
import logging
from dataclasses import dataclass, field
from typing import Protocol

from fastapi import HTTPException, status

from app.core.config import Settings
from app.services.llm_service import _classify_llm_error

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 40.0


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LlmReply:
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    raw: list | None = None  # bloques originales de Claude: se reenvian tal cual (incluido el pensamiento)


class LlmClient(Protocol):
    async def complete(self, messages: list[dict], tools: list[dict] | None) -> LlmReply: ...


def _llm_error(code: str, message: str, http_status: int = status.HTTP_503_SERVICE_UNAVAILABLE) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"codigo": code, "error": message, "detalles": {}})


class OpenAICompatibleClient:
    """Cualquier proveedor con API compatible con OpenAI (DeepSeek, NVIDIA NIM, etc.)."""

    def __init__(self, api_key: str, base_url: str, model: str, max_tokens: int):
        self._api_key = api_key
        self._base_url = base_url
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, messages: list[dict], tools: list[dict] | None) -> LlmReply:
        try:
            from openai import AsyncOpenAI
        except ImportError as error:
            raise _llm_error("COMPETENCIA_OPENAI_MISSING", "El backend no tiene instalada la dependencia openai.") from error

        client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url, timeout=LLM_TIMEOUT_SECONDS)
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
            "temperature": 0.1,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            response = await client.chat.completions.create(**kwargs)
        except Exception as error:
            code, message = _classify_llm_error(error)
            logger.error("Error LLM competencia [%s]: %s - %s", code, type(error).__name__, error)
            raise _llm_error(code.replace("RAG_", "COMPETENCIA_"), message) from error

        message = response.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("argumentos no son un objeto")
            except ValueError:
                arguments = {"_error": "argumentos invalidos"}
            calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
        usage = response.usage
        return LlmReply(
            content=message.content or "",
            tool_calls=calls,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
        )


CLAUDE_RECHAZO = "No puedo responder esa consulta."


def _a_claude(messages: list[dict]) -> tuple[str, list[dict]]:
    """Mensajes en formato OpenAI -> (system, mensajes de Claude). Los resultados de herramientas van en un
    mensaje user con bloques tool_result; turnos seguidos del mismo rol se juntan; el primero debe ser user."""
    system: list[str] = []
    salida: list[dict] = []

    def agregar(rol: str, bloques: list) -> None:
        if salida and salida[-1]["role"] == rol:
            salida[-1]["content"].extend(bloques)
        else:
            salida.append({"role": rol, "content": list(bloques)})

    for m in messages:
        rol = m["role"]
        if rol == "system":
            system.append(m["content"])
        elif rol == "tool":
            agregar("user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}])
        elif rol == "assistant" and m.get("_claude") is not None:
            agregar("assistant", m["_claude"])
        elif m.get("content"):
            agregar(rol, [{"type": "text", "text": m["content"]}])
    while salida and salida[0]["role"] != "user":
        salida.pop(0)
    return "\n\n".join(system), salida


class AnthropicClient:
    """Claude con la API de Anthropic (SDK oficial)."""

    def __init__(self, api_key: str, model: str, max_tokens: int):
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._tools: list[dict] | None = None

    async def complete(self, messages: list[dict], tools: list[dict] | None) -> LlmReply:
        from anthropic import AsyncAnthropic

        system, claude_messages = _a_claude(messages)
        kwargs: dict = {
            "model": self._model, "system": system, "messages": claude_messages,
            # Sin temperature (los modelos actuales la rechazan); el pensamiento cuenta en max_tokens.
            "max_tokens": max(self._max_tokens, 16000),
        }
        if tools:
            self._tools = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
                            "input_schema": t["function"]["parameters"]} for t in tools]
            kwargs["tools"] = self._tools
        elif self._tools:
            # Con herramientas ya usadas en la conversacion Claude exige sus definiciones: se mandan sin permitir llamarlas.
            kwargs["tools"] = self._tools
            kwargs["tool_choice"] = {"type": "none"}
        client = AsyncAnthropic(api_key=self._api_key, timeout=120.0)
        try:
            response = await client.messages.create(**kwargs)
        except Exception as error:
            code, message = _classify_llm_error(error)
            logger.error("Error LLM competencia Claude [%s]: %s - %s", code, type(error).__name__, error)
            raise _llm_error(code.replace("RAG_", "COMPETENCIA_"), message) from error

        if response.stop_reason == "refusal":
            return LlmReply(content=CLAUDE_RECHAZO, tokens_in=response.usage.input_tokens,
                            tokens_out=response.usage.output_tokens)
        calls = [
            ToolCall(id=b.id, name=b.name, arguments=b.input if isinstance(b.input, dict) else {"_error": "argumentos invalidos"})
            for b in response.content if b.type == "tool_use"
        ]
        return LlmReply(
            content="".join(b.text for b in response.content if b.type == "text"),
            tool_calls=calls,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            raw=list(response.content),
        )


def build_llm_client(settings: Settings) -> LlmClient:
    if settings.LLM_PROVIDER == "anthropic":
        if not settings.ANTHROPIC_API_KEY:
            raise _llm_error(
                "COMPETENCIA_LLM_NOT_CONFIGURED",
                "El chat de competencia no tiene la API key de Anthropic configurada.",
            )
        return AnthropicClient(
            api_key=settings.ANTHROPIC_API_KEY,
            model=settings.COMPETENCIA_MODEL or settings.DEEPSEEK_MODEL,
            max_tokens=settings.COMPETENCIA_MAX_TOKENS,
        )
    if not settings.DEEPSEEK_API_KEY:
        raise _llm_error(
            "COMPETENCIA_LLM_NOT_CONFIGURED",
            "El chat de competencia no tiene un proveedor de IA configurado en el backend.",
        )
    return OpenAICompatibleClient(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.COMPETENCIA_MODEL or settings.DEEPSEEK_MODEL,
        max_tokens=settings.COMPETENCIA_MAX_TOKENS,
    )
