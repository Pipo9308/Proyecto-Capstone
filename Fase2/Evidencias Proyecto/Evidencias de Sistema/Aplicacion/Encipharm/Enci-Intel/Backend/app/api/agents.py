from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
from app.api.auth import require_admin, require_auth, require_user_or_service
from app.api.rate_limiter import check_and_increment
from app.api import cache as _cache
from app.api.alerts import _iso_utc
from app.db import get_db
from app.scheduler import corriendo, marcar_huerfanas, run_agent_subprocess, update_agent_cron

router = APIRouter()


def _con_utc(doc: dict) -> dict:
    """Firestore devuelve fechas sin zona (en UTC): se envian marcadas como UTC para que el navegador
    las muestre en su hora local (antes salian 3 h corridas en Chile)."""
    return {k: _iso_utc(v) if isinstance(v, datetime) else v for k, v in doc.items()}


def _refrescar_cache(agent_id: str) -> None:
    """Tras ejecutar, programar o pausar, el panel debe ver el cambio enseguida y no la copia en cache."""
    _cache.invalidate("agents")
    _cache.invalidate(f"agent_runs:{agent_id}:10")  # el limite que usa el panel


def require_admin_or_service(caller: dict = Depends(require_user_or_service)) -> dict:
    """Un admin desde el panel o el disparador programado externo (GitHub Actions) con la API key de servicio."""
    return caller if caller.get("service") else require_admin(caller)

@router.get("/")
async def get_agents(_: dict = Depends(require_auth)):
    cached = _cache.get("agents")
    if cached:
        return cached
    db = get_db()
    agents_docs = await db.agents.find().to_list(length=None)
    agents = []
    for doc in agents_docs:
        doc_copy = {**doc, "id": str(doc.get("_id"))}
        if "_id" in doc_copy:
            del doc_copy["_id"]
        agents.append(_con_utc(doc_copy))
    result = {"success": True, "data": agents}
    _cache.set("agents", result, ttl=60)
    return result


@router.get("/{agent_id}/runs")
async def get_agent_runs(agent_id: str, limit: int = 10, _: dict = Depends(require_auth)):
    cache_key = f"agent_runs:{agent_id}:{limit}"
    cached = _cache.get(cache_key)
    if cached:
        return cached
    db = get_db()
    await marcar_huerfanas(db)
    runs_docs = await db.agent_runs.find({"agent_id": agent_id}).sort("started_at", -1).limit(limit).to_list(length=limit)
    runs = []
    for doc in runs_docs:
        run = {**doc, "id": str(doc.get("_id"))}
        if "_id" in run:
            del run["_id"]
        runs.append(_con_utc(run))
    result = {"success": True, "data": runs}
    # No cachear mientras el run mas reciente siga "running": el frontend hace
    # polling para reflejar en vivo cuando termina, y una cache de 30s lo
    # dejaria mostrando "running" durante ese tiempo aunque ya haya acabado.
    # Un run ya finalizado es inmutable, asi que cachearlo si es seguro.
    # Tampoco mientras el proceso del agente siga vivo: puede no haber escrito aun su corrida.
    if not corriendo(agent_id) and (not runs or runs[0].get("status") != "running"):
        _cache.set(cache_key, result, ttl=30)
    return result


@router.post("/{agent_id}/run")
async def run_agent_now(agent_id: str, admin=Depends(require_admin_or_service)):
    if not check_and_increment(f"agent_run:{admin.get('sub', 'service')}", limit=10, window="hour"):
        raise HTTPException(status_code=429, detail="Límite de ejecuciones alcanzado (10/hora).")
    
    db = get_db()
    query = {"_id": agent_id}
    doc = await db.agents.find_one(query)
    if not doc:
        # Fallback to string id if it was stored as string
        doc = await db.agents.find_one({"id": agent_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Agente no encontrado")

    if doc.get("status") == "idle" or doc.get("enabled") is False:
        raise HTTPException(status_code=400, detail="El agente está inactivo y no puede ejecutarse")

    # Trigger subprocess
    started = run_agent_subprocess(agent_id)
    if not started:
        raise HTTPException(status_code=500, detail=f"No se encontro el script del agente '{agent_id}'")
    _refrescar_cache(agent_id)
    return {"success": True, "message": "Ejecución local del agente iniciada en segundo plano"}


class ScheduleUpdate(BaseModel):
    schedule: str


@router.patch("/{agent_id}/schedule")
async def update_agent_schedule(agent_id: str, body: ScheduleUpdate, admin=Depends(require_admin)):
    parts = body.schedule.strip().split()
    if len(parts) != 5:
        raise HTTPException(status_code=400, detail="El schedule debe ser una expresión cron de 5 campos.")

    db = get_db()
    query = {"_id": agent_id}
    doc = await db.agents.find_one(query)
    if not doc:
        doc = await db.agents.find_one({"id": agent_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
            
        query = {"id": agent_id} # if fallback

    # MOCK: Update MongoDB without contacting GCP
    await db.agents.update_one(query, {"$set": {"schedule": body.schedule}})
    
    update_agent_cron(agent_id, body.schedule, enabled=doc.get("enabled", True))
    _refrescar_cache(agent_id)

    return {"success": True, "schedule": body.schedule}


@router.patch("/{agent_id}/enabled")
async def toggle_agent(agent_id: str, admin=Depends(require_admin)):
    db = get_db()
    query = {"_id": agent_id}
    doc = await db.agents.find_one(query)
    if not doc:
        doc = await db.agents.find_one({"id": agent_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Agente no encontrado")
        query = {"id": agent_id}

    enabled = not doc.get("enabled", True)

    # MOCK: Update MongoDB without contacting GCP
    await db.agents.update_one(
        query, 
        {"$set": {"enabled": enabled, "status": "active" if enabled else "idle"}}
    )
    
    update_agent_cron(agent_id, doc.get("schedule", ""), enabled=enabled)
    _refrescar_cache(agent_id)

    return {"success": True, "enabled": enabled}


@router.get("/{agent_id}")
async def get_agent_detail(agent_id: str, _: dict = Depends(require_auth)):
    db = get_db()
    query = {"_id": agent_id}
    doc = await db.agents.find_one(query)
    if not doc:
        doc = await db.agents.find_one({"id": agent_id})
        if not doc:
            return {"success": False, "data": None}
            
    doc_copy = {**doc, "id": str(doc.get("_id"))}
    if "_id" in doc_copy:
        del doc_copy["_id"]

    return {"success": True, "data": _con_utc(doc_copy)}