"""Llamadas al modelo de IA para los agentes (procesos aparte, sin la app web).

Usan el modelo de la pantalla "Modelo de IA" (Firestore app_settings/llm) o, sin nada guardado, las variables DEEPSEEK_*.
Con agentes_proveedor = "anthropic" (o el proveedor general en "anthropic") usan Claude con anthropic_api_key."""
import json
import re

from app import llm_settings

# Si el admin eligio Anthropic pero no un modelo para el agente.
ANTHROPIC_MODELO = "claude-opus-5-5"


def cargar_config(db, agente: str | None = None) -> dict | None:
    """Configuracion vigente del modelo ("competidores" o "sag" usan su modelo propio si lo hay), o None si no hay API key."""
    doc = db.app_settings.find_one({"_id": llm_settings.DOC_ID}) or {}
    guardado = llm_settings.leer(doc)
    general_anthropic = guardado.get("proveedor") == "anthropic"
    if guardado.get("agentes_proveedor") == "anthropic" or general_anthropic:
        key = guardado.get("anthropic_api_key")
        modelo = ((agente and doc.get(f"{agente}_model")) or (general_anthropic and guardado.get("model"))
                  or ANTHROPIC_MODELO)
        return {"proveedor": "anthropic", "api_key": key, "model": modelo} if key else None
    cfg = {**llm_settings.env_defaults(), **{k: v for k, v in guardado.items() if v and k in ("base_url", "model", "api_key")}}
    if agente and doc.get(f"{agente}_model"):
        cfg["model"] = doc[f"{agente}_model"]
    return cfg if cfg.get("api_key") else None


def describir_ia(cfg: dict | None) -> str:
    """Texto para el historial: que modelo usaria el agente si hay novedades (sin la key)."""
    if not cfg:
        return "sin configurar"
    return f"{'Anthropic' if cfg.get('proveedor') == 'anthropic' else 'Compatible OpenAI'} · {cfg['model']}"


def _texto_anthropic(cfg: dict, sistema: str, usuario: str, max_tokens: int) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=cfg["api_key"], timeout=120.0)
    # Los modelos actuales piensan antes de responder y eso cuenta en max_tokens: se deja holgura.
    respuesta = client.messages.create(
        model=cfg["model"], max_tokens=max(max_tokens, 16000), system=sistema,
        messages=[{"role": "user", "content": usuario}],
    )
    if respuesta.stop_reason == "refusal":
        raise RuntimeError("El modelo rechazó la solicitud")
    return "".join(b.text for b in respuesta.content if b.type == "text")


def pedir_json(cfg: dict, sistema: str, usuario: str, max_tokens: int = 1500):
    """Una llamada al modelo; devuelve el JSON parseado. Lanza si el modelo falla o no devuelve JSON valido."""
    if cfg.get("proveedor") == "anthropic":
        texto = _texto_anthropic(cfg, sistema, usuario, max_tokens)
    else:
        from openai import OpenAI

        client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"], timeout=40.0)
        respuesta = client.chat.completions.create(
            model=cfg["model"], temperature=0.1, max_tokens=max_tokens,
            messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        )
        texto = respuesta.choices[0].message.content or ""
    texto = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.MULTILINE)
    return json.loads(texto.strip())
