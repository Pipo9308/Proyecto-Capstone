from datetime import datetime, timezone

from app.core.odm import Session

from app.models_sql.intel import IntelLectura


def read_alert_ids(db: Session, user_id: str, alert_ids: list[str]) -> set[str]:
    """De los ids dados, los que este usuario ya leyo."""
    if not alert_ids:
        return set()
    rows = (
        db.query(IntelLectura.alertId)
        .filter(IntelLectura.usuarioId == user_id, IntelLectura.alertId.in_(alert_ids))
        .all()
    )
    return {row[0] for row in rows}


def mark_alert_read(db: Session, user_id: str, alert_id: str) -> None:
    """Idempotente: marcar dos veces la misma alerta no duplica la lectura."""
    exists = (
        db.query(IntelLectura.id)
        .filter(IntelLectura.usuarioId == user_id, IntelLectura.alertId == alert_id)
        .first()
    )
    if exists:
        return
    db.add(IntelLectura(usuarioId=user_id, alertId=alert_id, leidaEn=datetime.now(timezone.utc)))
    db.commit()
