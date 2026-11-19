import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("agente_competidores.detector")

# Umbrales: critical ≥80, high 60-79, medium 40-59, low <40
def _urgency_to_priority(urgency: int) -> str:
    if urgency >= 80:
        return "critical"
    if urgency >= 60:
        return "high"
    if urgency >= 40:
        return "medium"
    return "low"

_EXPIRY_DELTA = {
    "critical": timedelta(hours=24),
    "high":     timedelta(hours=72),
    "medium":   timedelta(days=7),
    "low":      timedelta(days=30),
}

def _expires_at(priority: str, created_at: datetime) -> datetime:
    return created_at + _EXPIRY_DELTA.get(priority, timedelta(days=30))

# Tipos que conoce el frontend (Alertas.tsx); el resto de tipos del modelo se muestra como "Inteligencia".
_TIPO_ALERTA = {"LANZAMIENTO": "LAUNCH", "REGULATORIO": "REGULATORY", "PRECIO": "PRICE"}

COL_NOTICIAS = "competitor_news"
COL_ALERTAS  = "alerts"


def cargar_noticias_previas(db) -> dict:
    docs = db[COL_NOTICIAS].find()
    return {doc["_id"]: doc for doc in docs}


def detectar_noticias_nuevas(noticias_actuales: list[dict], previas: dict) -> list[dict]:
    return [n for n in noticias_actuales if n["id"] not in previas]


def sincronizar_noticias(db, noticias: list[dict]):
    if not noticias:
        return
    ts    = datetime.now(timezone.utc)
    from app.firestore_db import UpdateOne
    ops = []
    for n in noticias:
        ops.append(UpdateOne({"_id": n["id"]}, {"$set": {**n, "updated_at": ts}}, upsert=True))
    if ops:
        db[COL_NOTICIAS].bulk_write(ops)
    logger.info(f"Sincronizadas {len(noticias)} noticias en Firestore")


def generar_alertas(db, nuevas_noticias: list[dict]) -> int:
    if not nuevas_noticias:
        return 0
    ts  = datetime.now(timezone.utc)
    from app.firestore_db import UpdateOne
    ops = []

    for n in nuevas_noticias:
        urgency  = n.get("urgencia", 55)  # lo fija el modelo si esta configurado
        priority = _urgency_to_priority(urgency)
        alert_id = f"comp_noticia_{n['id']}"
        tipo     = n.get("tipo")
        doc = {
            "type":       _TIPO_ALERTA.get(tipo, "LAUNCH" if not tipo else "FIELD_INTEL"),
            "subtype":    tipo or "NOTICIA",
            "title":      f"Nueva publicación {n.get('empresa', 'competidor').title()}: {n['titulo']}",
            "body":       n.get("resumen_ia") or n.get("resumen", "") or f"Ver artículo: {n['url']}",
            "urgency":    urgency,
            "priority":   priority,
            "source":     "Web competidor",
            "agent_id":   "agente_competidores",
            # La API deriva el competidor desde aqui (ver alerts._competitor_of).
            "data":       {"empresa": n.get("empresa"), "url": n.get("url")},
            "status":     "active",
            "created_at": ts,
            "expires_at": _expires_at(priority, ts),
        }
        ops.append(UpdateOne({"_id": alert_id}, {"$set": doc}, upsert=True))
        
    if ops:
        db[COL_ALERTAS].bulk_write(ops)

    logger.info(f"Alertas generadas: {len(nuevas_noticias)} noticias")
    return len(nuevas_noticias)