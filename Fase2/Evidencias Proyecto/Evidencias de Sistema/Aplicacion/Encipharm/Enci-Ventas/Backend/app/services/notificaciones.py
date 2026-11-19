"""Notificaciones dentro de la web (RQ-01).

Los avisos se crean en la misma transaccion del hecho que los origina (`crear` no hace commit).
Las alertas de Enci-Intel se detectan con un sondeo que se dispara cuando alguien consulta sus
avisos (con un tiempo minimo entre sondeos): Ventas no tiene planificador.
"""
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.odm import or_
from app.core.odm import Session

from app.models_sql.notificacion import Notificacion
from app.models_sql.user import User

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90
INTEL_PRIORITIES = ("critical", "high")
TIPO_ALERTA = "alerta_intel"
TIPO_CLIENTE = "cliente_asignado"
TIPO_PROPUESTA = "propuesta_estado"
TIPO_DOCUMENTO = "documento_rag"
TIPO_VISITA = "visita_proxima"

# Control de frecuencia por proceso: un sondeo de Intel y una limpieza a la vez, no uno por consulta.
_last_run: dict[str, float] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def crear(
    db: Session, usuario_id: str, tipo: str, titulo: str, *,
    mensaje: str | None = None, enlace: str | None = None, referencia: str | None = None,
) -> Notificacion | None:
    """Agrega el aviso a la sesion (sin commit). Con `referencia`, el mismo hecho avisa una sola vez."""
    if referencia and (
        db.query(Notificacion.id)
        .filter(Notificacion.usuarioId == usuario_id, Notificacion.tipo == tipo, Notificacion.referencia == referencia)
        .first()
    ):
        return None
    notification = Notificacion(
        usuarioId=usuario_id, tipo=tipo, titulo=titulo[:200], mensaje=mensaje, enlace=enlace, referencia=referencia,
    )
    db.add(notification)
    return notification


def _serialize(n: Notificacion) -> dict[str, Any]:
    return {
        "id": n.id, "tipo": n.tipo, "titulo": n.titulo, "mensaje": n.mensaje, "enlace": n.enlace,
        "leida": n.leida, "createdAt": n.createdAt,
    }


def listar(db: Session, usuario_id: str, *, solo_no_leidas: bool, limit: int, offset: int) -> dict[str, Any]:
    query = db.query(Notificacion).filter(Notificacion.usuarioId == usuario_id)
    unread = query.filter(Notificacion.leida.is_(False)).count()
    if solo_no_leidas:
        query = query.filter(Notificacion.leida.is_(False))
    total = query.count()
    rows = query.order_by(Notificacion.createdAt.desc(), Notificacion.id).offset(offset).limit(limit).all()
    return {"items": [_serialize(n) for n in rows], "total": total, "noLeidas": unread}


def marcar_leida(db: Session, usuario_id: str, notification_id: str) -> bool:
    """False si el aviso no existe o es de otro usuario."""
    row = db.query(Notificacion).filter(Notificacion.id == notification_id, Notificacion.usuarioId == usuario_id).first()
    if row is None:
        return False
    row.leida = True
    db.commit()
    return True


def marcar_todas(db: Session, usuario_id: str) -> int:
    count = (
        db.query(Notificacion)
        .filter(Notificacion.usuarioId == usuario_id, Notificacion.leida.is_(False))
        .update({"leida": True}, synchronize_session=False)
    )
    db.commit()
    return count


def purgar(db: Session, dias: int = RETENTION_DAYS) -> int:
    removed = db.query(Notificacion).filter(Notificacion.createdAt < _now() - timedelta(days=dias)).delete()
    db.commit()
    return removed


# ── Destinatarios ────────────────────────────────────────────────────────────

def notificar_admins(db: Session, tipo: str, titulo: str, **kwargs) -> None:
    for (user_id,) in db.query(User.id).filter(User.rol == "admin", User.activo.is_(True)).all():
        crear(db, user_id, tipo, titulo, **kwargs)


def usuarios_con_acceso_intel(db: Session) -> list[str]:
    rows = db.query(User.id).filter(User.activo.is_(True), or_(User.accesoInteligencia.is_(True), User.rol == "admin")).all()
    return [row[0] for row in rows]


# ── Sondeo de alertas de Enci-Intel ──────────────────────────────────────────

def _created_at(alert: dict) -> datetime | None:
    text = str(alert.get("created_at") or "")
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


async def sync_intel_alerts(db: Session, intel, lookback_hours: int) -> int:
    """Avisa de las alertas criticas y altas recientes a quienes tienen acceso a Inteligencia."""
    recipients = usuarios_con_acceso_intel(db)
    if not recipients:
        return 0
    since = _now() - timedelta(hours=lookback_hours)
    created = 0
    for priority in INTEL_PRIORITIES:
        result = await intel.get_alertas(priority=priority, limit=50)
        for alert in result.get("data", []):
            moment = _created_at(alert)
            if not alert.get("id") or (moment is not None and moment < since):
                continue
            label = "crítica" if priority == "critical" else "alta"
            detail = " · ".join(part for part in (alert.get("competitor"), f"Prioridad {label}") if part)
            for user_id in recipients:
                if crear(db, user_id, TIPO_ALERTA, alert.get("title") or "Nueva alerta", mensaje=detail,
                         enlace="/inteligencia", referencia=str(alert["id"])[:120]):
                    created += 1
    db.commit()
    return created


def _due(key: str, every_seconds: float) -> bool:
    now = time.monotonic()
    if now - _last_run.get(key, float("-inf")) < every_seconds:
        return False
    _last_run[key] = now
    return True


async def mantenimiento(session_factory, intel, *, poll_seconds: float, lookback_hours: int) -> None:
    """Sondeo de Intel (cada `poll_seconds`), recordatorios de visitas (cada minuto) y purga de avisos viejos
    (cada hora). Nunca lanza."""
    try:
        if poll_seconds > 0 and intel is not None and _due("intel", poll_seconds):
            with session_factory() as db:
                await sync_intel_alerts(db, intel, lookback_hours)
        if _due("recordatorios", 60):
            from app.services.eventos import sync_reminders  # import tardio: eventos usa este modulo

            with session_factory() as db:
                sync_reminders(db)
        if _due("purga", 3600):
            with session_factory() as db:
                purgar(db)
    except Exception:
        # Un fallo de Intel no debe tumbar la consulta de avisos; se reintenta al vencer el intervalo.
        logger.warning("No se pudo actualizar las notificaciones", exc_info=True)
