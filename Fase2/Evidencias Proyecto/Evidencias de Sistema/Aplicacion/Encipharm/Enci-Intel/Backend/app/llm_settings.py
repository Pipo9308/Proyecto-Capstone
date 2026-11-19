"""Modelo de IA editable desde el frontend (coleccion app_settings, documento "llm").

Lo guardado manda sobre las variables de entorno; sin nada guardado rigen DEEPSEEK_*.
La API key se guarda cifrada (Fernet, clave derivada de JWT_SECRET_KEY): si ese secreto cambia, hay que volver a pegarla.
shortcut: la copia guardada vive en memoria del proceso; con varias instancias de Intel, reiniciar para sincronizarlas."""
import base64
import hashlib
import logging
import os

from cryptography.fernet import Fernet, InvalidToken

from app.db import get_db

logger = logging.getLogger(__name__)

DOC_ID = "llm"
RAG_DOC_ID = "rag"
# proveedor: "" = compatible con OpenAI (base_url + api_key); "anthropic" = Claude con anthropic_api_key.
# competidores_model / sag_model: modelo propio de cada agente; vacio = el general.
# agentes_proveedor "anthropic": los agentes usan Claude aunque el general sea otro; "" = el mismo que el general.
CAMPOS = ("proveedor", "base_url", "model", "competencia_model", "api_key", "competidores_model", "sag_model",
          "agentes_proveedor", "anthropic_api_key")
SECRETOS = ("api_key", "anthropic_api_key")
RAG_CAMPOS = ("instrucciones", "temperatura", "max_tokens", "documentos", "umbral")
_PREFIJO = "enc:"

_saved: dict = {}
_rag: dict = {}


def _fernet() -> Fernet:
    secreto = os.environ.get("JWT_SECRET_KEY", "")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secreto.encode()).digest()))


def cifrar(valor: str) -> str:
    return _PREFIJO + _fernet().encrypt(valor.encode()).decode() if valor else ""


def descifrar(valor: str | None) -> str:
    if not valor or not valor.startswith(_PREFIJO):
        return valor or ""  # guardada antes del cifrado
    try:
        return _fernet().decrypt(valor[len(_PREFIJO):].encode()).decode()
    except InvalidToken:
        logger.warning("No se pudo descifrar la API key de IA guardada (¿cambió JWT_SECRET_KEY?); vuelve a pegarla")
        return ""


def leer(doc: dict) -> dict:
    """Campos del documento guardado, con las API keys ya descifradas."""
    return {k: descifrar(doc.get(k)) if k in SECRETOS else doc.get(k) for k in CAMPOS}


def env_defaults() -> dict:
    return {
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "api_key": os.environ.get("DEEPSEEK_API_KEY", "").strip(),
    }


def saved() -> dict:
    """Solo lo que un admin guardo (campos vacios fuera). Ventas lo aplica sobre su propio entorno."""
    return {k: v for k, v in _saved.items() if k in CAMPOS and v}


def effective() -> dict:
    return {**env_defaults(), **saved()}


def es_anthropic(cfg: dict) -> bool:
    return cfg.get("proveedor") == "anthropic"


async def load() -> None:
    db = get_db()
    doc = await db.app_settings.find_one({"_id": DOC_ID}) or {}
    _saved.clear()
    _saved.update(leer(doc))
    if doc.get("api_key") and not doc["api_key"].startswith(_PREFIJO):  # key guardada en claro antes: se cifra una vez
        await db.app_settings.update_one({"_id": DOC_ID}, {"$set": {"api_key": cifrar(doc["api_key"])}})
    rag_doc = await db.app_settings.find_one({"_id": RAG_DOC_ID}) or {}
    _rag.clear()
    _rag.update({k: rag_doc[k] for k in RAG_CAMPOS if rag_doc.get(k) not in (None, "")})


async def save(values: dict, updated_by: str, updated_at) -> None:
    data = {**{k: values.get(k) or "" for k in CAMPOS}, "updated_by": updated_by, "updated_at": updated_at}
    await get_db().app_settings.update_one({"_id": DOC_ID}, {"$set": {**data, **{k: cifrar(data[k]) for k in SECRETOS}}},
                                           upsert=True)
    _saved.clear()
    _saved.update({k: data[k] for k in CAMPOS})


def rag_saved() -> dict:
    """Ajustes del Consultor Vet guardados por un admin (los que falten usan los valores por defecto del motor)."""
    return dict(_rag)


async def save_rag(values: dict, updated_by: str, updated_at) -> None:
    data = {k: values[k] for k in RAG_CAMPOS}
    await get_db().app_settings.update_one(
        {"_id": RAG_DOC_ID}, {"$set": {**data, "updated_by": updated_by, "updated_at": updated_at}}, upsert=True)
    _rag.clear()
    _rag.update(data)
