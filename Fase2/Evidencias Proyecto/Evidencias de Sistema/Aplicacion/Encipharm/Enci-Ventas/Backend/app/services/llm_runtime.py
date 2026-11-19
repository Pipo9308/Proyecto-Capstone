"""Modelo de IA que un admin guarda en Enci-Intel (pantalla "Modelo de IA").

Se consulta con la API key de servicio y se cachea; si Intel no responde o no hay nada guardado,
rigen las variables de entorno de Ventas."""
import logging
import time

from app.services.enci_intel import EnciIntelService

logger = logging.getLogger(__name__)

TTL_SECONDS = 60
_CAMPOS = {
    "proveedor": "LLM_PROVIDER",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "api_key": "DEEPSEEK_API_KEY",
    "base_url": "DEEPSEEK_BASE_URL",
    "model": "DEEPSEEK_MODEL",
    "competencia_model": "COMPETENCIA_MODEL",
}
_cache: dict = {"at": 0.0, "value": {}}


async def llm_overrides() -> dict:
    """Campos de Settings a pisar (vacio = ninguno). Un fallo tambien se cachea para no frenar cada chat."""
    if time.monotonic() - _cache["at"] < TTL_SECONDS:
        return _cache["value"]
    try:
        saved = await EnciIntelService().get_llm_settings()
        value = {_CAMPOS[k]: v for k, v in saved.items() if k in _CAMPOS and v}
    except Exception as error:
        logger.warning("Modelo de IA de Enci-Intel no disponible, se usa el entorno: %s", type(error).__name__)
        value = {}
    _cache.update(at=time.monotonic(), value=value)
    return value
