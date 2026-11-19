import time
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import llm_settings
from app.api.auth import require_admin, require_user_or_service
from app.rag import engine

router = APIRouter()


class LlmSettingsIn(BaseModel):
    proveedor: Literal["", "anthropic"] = ""  # "" = compatible con OpenAI (base_url + api_key)
    base_url: str = Field(default="", max_length=300)  # no se usa con Anthropic
    model: str = Field(min_length=1, max_length=120)
    competencia_model: str = Field(default="", max_length=120)
    competidores_model: str = Field(default="", max_length=120)
    sag_model: str = Field(default="", max_length=120)
    api_key: str = Field(default="", max_length=500)  # vacio = conservar la actual
    agentes_proveedor: Literal["", "anthropic"] = ""  # "" = el proveedor general de arriba
    anthropic_api_key: str = Field(default="", max_length=500)  # vacio = conservar la actual


class AnthropicKeyIn(BaseModel):
    api_key: str = Field(default="", max_length=500)  # vacio = la guardada


class RagIn(BaseModel):
    instrucciones: str = Field(min_length=20, max_length=8000)
    temperatura: float = Field(ge=0, le=1)
    max_tokens: int = Field(ge=256, le=4096)
    documentos: int = Field(ge=1, le=10)
    umbral: float = Field(ge=0, le=0.95)


def _validar(body: LlmSettingsIn) -> dict:
    anthropic = body.proveedor == "anthropic"
    base_url = body.base_url.strip().rstrip("/")
    if not anthropic and not base_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="La URL del proveedor debe empezar con https://")
    values = {
        "proveedor": body.proveedor,
        "base_url": base_url,
        "model": body.model.strip(),
        "competencia_model": body.competencia_model.strip(),
        "competidores_model": body.competidores_model.strip(),
        "sag_model": body.sag_model.strip(),
        "api_key": body.api_key.strip() or llm_settings.saved().get("api_key", ""),
        "agentes_proveedor": body.agentes_proveedor,
        "anthropic_api_key": body.anthropic_api_key.strip() or llm_settings.saved().get("anthropic_api_key", ""),
    }
    # La key del entorno solo sirve para el proveedor del entorno.
    if not anthropic and not values["api_key"] and base_url != llm_settings.env_defaults()["base_url"].rstrip("/"):
        raise HTTPException(status_code=400, detail="Ingresa la API key de este proveedor")
    if (anthropic or values["agentes_proveedor"] == "anthropic") and not values["anthropic_api_key"]:
        raise HTTPException(status_code=400, detail="Ingresa la API key de Anthropic")
    return values


def _pista(key: str) -> str:
    return key[-4:] if len(key) > 8 else ""


def _public() -> dict:
    cfg = llm_settings.effective()
    key = cfg.get("api_key", "")
    anthropic_key = llm_settings.saved().get("anthropic_api_key", "")
    return {
        "proveedor": cfg.get("proveedor", ""),
        "base_url": cfg["base_url"],
        "model": cfg["model"],
        "competencia_model": llm_settings.saved().get("competencia_model", ""),
        "competidores_model": llm_settings.saved().get("competidores_model", ""),
        "sag_model": llm_settings.saved().get("sag_model", ""),
        "api_key_set": bool(key),
        "api_key_hint": _pista(key),
        "agentes_proveedor": llm_settings.saved().get("agentes_proveedor", ""),
        "anthropic_key_set": bool(anthropic_key),
        "anthropic_key_hint": _pista(anthropic_key),
        "source": "guardado" if llm_settings.saved() else "entorno",
    }


@router.get("/")
async def get_settings(_: dict = Depends(require_admin)):
    return {"success": True, "data": _public()}


@router.put("/")
async def put_settings(body: LlmSettingsIn, admin: dict = Depends(require_admin)):
    values = _validar(body)
    await llm_settings.save(values, admin.get("email", ""), datetime.now(timezone.utc))
    return {"success": True, "data": _public()}


@router.post("/test")
async def test_settings(body: LlmSettingsIn, _: dict = Depends(require_admin)):
    """Una llamada minima con los valores del formulario, sin guardarlos."""
    values = _validar(body)
    pregunta = [{"role": "user", "content": "Responde solo: OK"}]
    inicio = time.monotonic()
    try:
        if body.proveedor == "anthropic":
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(api_key=values["anthropic_api_key"], timeout=60.0)
            await client.messages.create(model=values["model"], messages=pregunta, max_tokens=1024)
        else:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=values["api_key"] or llm_settings.env_defaults()["api_key"],
                                 base_url=values["base_url"], timeout=20.0)
            await client.chat.completions.create(model=values["model"], messages=pregunta, max_tokens=8)
    except Exception as error:  # el mensaje del proveedor no incluye la key
        return {"success": True, "data": {"ok": False, "detail": f"{type(error).__name__}: {str(error)[:300]}"}}
    return {"success": True, "data": {"ok": True, "ms": int((time.monotonic() - inicio) * 1000)}}


@router.post("/anthropic/modelos")
async def anthropic_models(body: AnthropicKeyIn, _: dict = Depends(require_admin)):
    """Conecta con Anthropic (key del formulario o la guardada) y devuelve los modelos disponibles para esa key."""
    key = body.api_key.strip() or llm_settings.saved().get("anthropic_api_key", "")
    if not key:
        raise HTTPException(status_code=400, detail="Ingresa la API key de Anthropic")
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=key, timeout=20.0)
    try:
        modelos = [{"id": m.id, "nombre": m.display_name} async for m in client.models.list()]
    except anthropic.AuthenticationError:
        return {"success": True, "data": {"ok": False, "detail": "Anthropic rechazó la API key."}}
    except Exception as error:  # el mensaje del proveedor no incluye la key
        return {"success": True, "data": {"ok": False, "detail": f"{type(error).__name__}: {str(error)[:300]}"}}
    return {"success": True, "data": {"ok": True, "modelos": modelos}}


def _rag_public() -> dict:
    return {
        "vigente": engine.rag_config(),
        "por_defecto": engine.RAG_DEFAULTS,
        "reglas": engine._RULES.strip(),
        "source": "guardado" if llm_settings.rag_saved() else "por_defecto",
    }


@router.get("/rag")
async def get_rag(_: dict = Depends(require_admin)):
    return {"success": True, "data": _rag_public()}


@router.put("/rag")
async def put_rag(body: RagIn, admin: dict = Depends(require_admin)):
    await llm_settings.save_rag(body.model_dump(), admin.get("email", ""), datetime.now(timezone.utc))
    return {"success": True, "data": _rag_public()}


@router.get("/runtime")
async def runtime_settings(caller: dict = Depends(require_user_or_service)):
    """Lo guardado, con la key, para Enci-Ventas (solo con la API key de servicio).
    La key de Anthropic sale solo si los chats usan Anthropic (si es solo para los agentes, Ventas no la necesita)."""
    if not caller.get("service"):
        raise HTTPException(status_code=403, detail="Solo servicios")
    guardado = llm_settings.saved()
    if not llm_settings.es_anthropic(guardado):
        guardado.pop("anthropic_api_key", None)
    return guardado
