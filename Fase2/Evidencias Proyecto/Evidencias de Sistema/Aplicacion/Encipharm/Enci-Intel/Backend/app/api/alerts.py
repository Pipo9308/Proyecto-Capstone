import re
from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone
from app.api import cache as _cache
from app.db import get_db
from app.api.auth import require_user_or_service

router = APIRouter()

_SAG_EXCLUIR = {"status", "cancelled_at", "updated_at"}

CAMPOS_ALERTA = {
    "title", "body", "description", "type", "subtype",
    "priority", "urgency", "source", "agent_id", "status",
    "created_at", "leida", "expires_at", "data",
}

# Umbrales: critical ≥80, high 60-79, medium 40-59, low <40
def _resolve_priority(alert: dict) -> str:
    if alert.get("priority"):
        return str(alert["priority"]).lower()
    urgency = alert.get("urgency")
    if isinstance(urgency, (int, float)):
        if urgency >= 80:
            return "critical"
        if urgency >= 60:
            return "high"
        if urgency >= 40:
            return "medium"
        return "low"
    return "low"

# Ventas (proxy servicio a servicio) y los frontends consumen este feed.
_COMPETITOR_KEYS = ("empresa", "Importador o Registrante", "Empresa Fabricante")
_TITLE_COMPETITOR = re.compile(r"publicaci[oó]n\s+(.+?):")

MAX_ALERTS_LOADED = 1000


def _competitor_of(alert: dict) -> str | None:
    """Competidor de la alerta: los agentes no guardan un campo propio, asi que se
    deriva del dato de origen (SAG: importador/fabricante; noticias: titulo)."""
    data = alert.get("data") or {}
    for key in _COMPETITOR_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    match = _TITLE_COMPETITOR.search(alert.get("title") or "")
    return match.group(1).strip() if match else None


def _serialize(doc: dict) -> dict:
    data = {k: v for k, v in doc.items() if k in CAMPOS_ALERTA}
    data["id"] = str(doc["_id"])
    return data


def _iso_utc(value: datetime) -> str:
    """Motor devuelve datetimes sin zona (siempre UTC): se marcan como UTC para que
    los clientes calculen bien "hace cuanto llego" en cualquier huso horario."""
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).isoformat()


def _finalize(data: dict) -> dict:
    data["priority"] = _resolve_priority(data)
    for campo in ("created_at", "expires_at"):
        if campo in data and isinstance(data[campo], datetime):
            data[campo] = _iso_utc(data[campo])
    data["competitor"] = _competitor_of(data)
    return data


async def _enrich_cancellations(db, alerts: list[dict]) -> None:
    """Completa las alertas SAG de cancelacion con los datos de sag_productos."""
    indices_sag = [
        (i, (a.get("data") or {}).get("registro"))
        for i, a in enumerate(alerts)
        if a.get("agent_id") == "agente_sag"
        and a.get("subtype") == "CANCELACION"
        and (a.get("data") or {}).get("registro")
    ]
    if not indices_sag:
        return
    registros_uniq = list({r for _, r in indices_sag})
    docs_sag = await db.sag_productos.find({"_id": {"$in": registros_uniq}}).to_list(length=len(registros_uniq))
    productos = {
        str(doc["_id"]): {k: v for k, v in doc.items() if k not in _SAG_EXCLUIR and v not in (None, "", float("nan")) and k != "_id"}
        for doc in docs_sag
    }
    for i, reg_id in indices_sag:
        if reg_id in productos:
            current = alerts[i].get("data") or {}
            alerts[i]["data"] = {**current, **productos[reg_id]}
            alerts[i]["competitor"] = _competitor_of(alerts[i])


async def _load_active_alerts() -> dict:
    """Todas las alertas, vencidas incluidas (mas recientes primero) y sus conteos. Se cachea 120 s."""
    cached = _cache.get("alerts_all")
    if cached:
        return cached

    db = get_db()
    docs = await db.alerts.find().sort("created_at", -1).limit(MAX_ALERTS_LOADED).to_list(length=MAX_ALERTS_LOADED)

    alerts = []
    for doc in docs:
        alerts.append(_finalize(_serialize(doc)))

    alerts.sort(key=lambda a: a.get("created_at") or "", reverse=True)
    await _enrich_cancellations(db, alerts)

    counts = {
        "total": len(alerts),
        "critical": sum(1 for a in alerts if a["priority"] == "critical"),
        "high": sum(1 for a in alerts if a["priority"] == "high"),
        "medium": sum(1 for a in alerts if a["priority"] == "medium"),
        "low": sum(1 for a in alerts if a["priority"] == "low"),
    }
    result = {"alerts": alerts, "counts": counts}
    _cache.set("alerts_all", result, ttl=120)
    return result


@router.get("/")
async def get_alerts(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    priority: str | None = None,
    alert_type: str | None = Query(None, alias="type"),
    competitor: str | None = None,
    _: dict = Depends(require_user_or_service),
):
    """Feed de alertas vigentes con filtros y paginacion. `counts` siempre describe
    todas las vigentes; `total` es la cantidad que cumple los filtros."""
    loaded = await _load_active_alerts()
    alerts = loaded["alerts"]

    if priority:
        wanted = priority.strip().lower()
        alerts = [a for a in alerts if a["priority"] == wanted]
    if alert_type:
        wanted = alert_type.strip().lower()
        alerts = [a for a in alerts if wanted in (str(a.get("type", "")).lower(), str(a.get("subtype", "")).lower())]
    if competitor:
        needle = competitor.strip().lower()
        alerts = [a for a in alerts if needle in (a.get("competitor") or "").lower()]

    page = alerts[offset:offset + limit]
    return {
        "success": True,
        "counts": loaded["counts"],
        "total": len(alerts),
        "limit": limit,
        "offset": offset,
        "has_more": offset + len(page) < len(alerts),
        "data": page,
    }


@router.get("/{alert_id}")
async def get_alert(alert_id: str, _: dict = Depends(require_user_or_service)):
    db = get_db()
    doc = await db.alerts.find_one({"_id": alert_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")
    alert = _finalize(_serialize(doc))
    await _enrich_cancellations(db, [alert])
    return {"success": True, "data": alert}
