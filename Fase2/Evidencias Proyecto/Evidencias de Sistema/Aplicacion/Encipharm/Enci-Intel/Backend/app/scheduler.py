import subprocess
import sys
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("enci_scheduler")
# Los horarios del panel ("Diario a las 8 AM") son hora de Chile, con cambio de horario incluido.
ZONA = "America/Santiago"
scheduler = AsyncIOScheduler(timezone=ZONA)

BACKEND_DIR = Path(__file__).resolve().parents[1]

# Se crean al arrancar si faltan; sin ellos el panel no puede ejecutar ni programar nada. Horas de Chile (ZONA).
AGENTES_POR_DEFECTO = {
    "agente_sag": {"name": "Agente SAG", "description": "Monitoreo de registros SAG de productos",
                   "schedule": "0 8 * * *"},
    "agente_competidores": {"name": "Agente Competidores", "description": "Noticias de Drag Pharma, Zoetis y Agrovet",
                            "schedule": "30 8 * * *"},
}
# Horarios por defecto de antes, escritos en UTC (8:00 y 8:30 de Chile en verano): se pasan a hora de Chile.
HORARIOS_UTC_ANTIGUOS = {"agente_sag": "0 11 * * *", "agente_competidores": "30 11 * * *"}
# Una corrida "running" mas vieja que esto quedo huerfana (proceso muerto por reinicio o falta de memoria).
HUERFANA_TRAS = timedelta(hours=2)

_procesos: dict[str, subprocess.Popen] = {}


def _resolve_agent_script(agent_id: str) -> Path | None:
    """Los ids en Mongo usan la palabra completa en espanol ("agente_sag")
    pero las carpetas reales usan el prefijo en ingles con guion
    ("agent-sag"). Antes solo se probaba agent_id.replace('_', '-')
    ("agente-sag"), que nunca coincidia con ninguna carpeta real."""
    candidatos = [
        agent_id,
        agent_id.replace("_", "-"),
        agent_id.replace("agente_", "agent-").replace("_", "-"),
        agent_id.replace("agente-", "agent-"),
    ]
    for candidato in candidatos:
        path = BACKEND_DIR / "agents" / candidato / "main.py"
        if path.exists():
            return path
    return None


def corriendo(agent_id: str) -> bool:
    """True si este proceso lanzo el agente y sigue vivo (aunque aun no haya registrado su corrida)."""
    proceso = _procesos.get(agent_id)
    return bool(proceso and proceso.poll() is None)


def run_agent_subprocess(agent_id: str) -> bool:
    logger.info(f"Running agent subprocess: {agent_id}")
    previo = _procesos.get(agent_id)
    if previo and previo.poll() is None:
        logger.info(f"{agent_id} sigue corriendo; no se lanza otra corrida")
        return True

    script_path = _resolve_agent_script(agent_id)
    if not script_path:
        logger.error(f"Agent script not found for {agent_id}")
        return False

    # cwd fijo: los agentes usan rutas relativas a Backend. La salida va a los logs del backend (stdout heredado).
    _procesos[agent_id] = subprocess.Popen([sys.executable, str(script_path)], cwd=BACKEND_DIR)
    logger.info(f"Started subprocess for {agent_id} at {script_path}")
    return True


async def marcar_huerfanas(db) -> int:
    """Pasa a "failure" las corridas que siguen en "running" mucho despues de empezar."""
    limite = datetime.now(timezone.utc).replace(tzinfo=None) - HUERFANA_TRAS
    total = 0
    for run in await db.agent_runs.find({"status": "running"}).to_list(length=None):
        inicio = run.get("started_at")
        if isinstance(inicio, datetime) and inicio.replace(tzinfo=None) < limite:
            await db.agent_runs.update_one({"_id": run["_id"]}, {"$set": {
                "status": "failure", "error": "La corrida no terminó (proceso interrumpido)",
                "ended_at": datetime.now(timezone.utc)}})
            total += 1
    return total


async def preparar_agentes(db) -> None:
    """Al arrancar: crea los agentes que falten (o les pone horario), cierra corridas huerfanas y restaura los cron."""
    for agent_id, base in AGENTES_POR_DEFECTO.items():
        doc = await db.agents.find_one({"_id": agent_id})
        if not doc:
            await db.agents.insert_one({"_id": agent_id, **base, "enabled": True, "status": "active"})
        elif not doc.get("schedule") or doc["schedule"] == HORARIOS_UTC_ANTIGUOS[agent_id]:
            await db.agents.update_one({"_id": agent_id}, {"$set": {"schedule": base["schedule"]}})
    huerfanas = await marcar_huerfanas(db)
    if huerfanas:
        logger.warning(f"{huerfanas} corridas de agentes quedaron a medias y se marcaron como fallidas")
    for agent in await db.agents.find().to_list(length=None):
        update_agent_cron(str(agent["_id"]), agent.get("schedule", ""), enabled=agent.get("enabled", True))


def update_agent_cron(agent_id: str, schedule: str, enabled: bool = True):
    job_id = f"job_{agent_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    if enabled and schedule:
        parts = schedule.split()
        if len(parts) == 5:
            # Simple conversion from cron to APScheduler CronTrigger
            from apscheduler.triggers.cron import CronTrigger
            try:
                trigger = CronTrigger(
                    minute=parts[0],
                    hour=parts[1],
                    day=parts[2],
                    month=parts[3],
                    day_of_week=parts[4],
                    timezone=ZONA,  # sin esto CronTrigger usa la zona del servidor (UTC en Docker/Render)
                )
                scheduler.add_job(
                    run_agent_subprocess,
                    trigger=trigger,
                    args=[agent_id],
                    id=job_id,
                    replace_existing=True
                )
                logger.info(f"Added cron job for {agent_id} with schedule: {schedule}")
            except Exception as e:
                logger.error(f"Failed to parse cron '{schedule}' for {agent_id}: {e}")

def start_scheduler():
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler stopped")
