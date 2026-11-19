"""Calendario interno (RQ-02): visitas, reuniones y llamadas planificadas con clientes.

El vendedor ve y edita las suyas; supervisor y admin ven las de todos (con filtro por vendedor).
Al marcar una visita como realizada queda registrada en el historial del cliente (una interaccion).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from app.core.odm import Session

from app.models_sql.cliente import Cliente
from app.models_sql.comercial import Interaction, Opportunity
from app.models_sql.evento import Evento
from app.models_sql.user import User
from app.services import notificaciones
from app.services.comercial import assert_cliente_visible
from app.services.clientes import ensure_assignee_exists

MAX_RANGE_DAYS = 93
MAX_RESULTS = 500
INTERACTION_TYPE = {"presencial": "visita", "virtual": "reunion", "llamada": "llamada"}
FROZEN_FIELDS = {"estado", "inicio", "fin", "tipo"}


def _error(http_status: int, message: str) -> HTTPException:
    return HTTPException(status_code=http_status, detail=message)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _serialize(event: Evento, clientes: dict[str, str], vendedores: dict[str, str]) -> dict[str, Any]:
    return {
        "id": event.id, "clienteId": event.clienteId, "clienteNombre": clientes.get(event.clienteId),
        "oportunidadId": event.oportunidadId, "vendedorUid": event.vendedorUid,
        "vendedorNombre": vendedores.get(event.vendedorUid), "tipo": event.tipo, "inicio": event.inicio,
        "fin": event.fin, "lugar": event.lugar, "notas": event.notas, "estado": event.estado,
        "interaccionId": event.interaccionId,
    }


def _serialize_many(db: Session, events: list[Evento]) -> list[dict[str, Any]]:
    client_ids = {e.clienteId for e in events}
    seller_ids = {e.vendedorUid for e in events}
    clientes = (
        {c.id: c.empresa or c.nombre for c in db.query(Cliente.id, Cliente.empresa, Cliente.nombre).filter(Cliente.id.in_(client_ids))}
        if client_ids else {}
    )
    vendedores = {u.id: u.nombre for u in db.query(User.id, User.nombre).filter(User.id.in_(seller_ids))} if seller_ids else {}
    return [_serialize(e, clientes, vendedores) for e in events]


def _get_editable(db: Session, event_id: str, user: dict) -> Evento:
    event = db.query(Evento).filter(Evento.id == event_id).first()
    if event is None:
        raise _error(status.HTTP_404_NOT_FOUND, "Evento no encontrado")
    if user["rol"] == "vendedor" and event.vendedorUid != user["uid"]:
        raise _error(status.HTTP_403_FORBIDDEN, "No tienes permisos para este evento")
    return event


def _check_opportunity(db: Session, opportunity_id: str | None, cliente_id: str) -> None:
    if not opportunity_id:
        return
    opportunity = db.query(Opportunity).filter(Opportunity.id == opportunity_id).first()
    if opportunity is None or opportunity.clienteId != cliente_id:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "La oportunidad no existe o no pertenece al cliente")


def list_eventos(
    db: Session, user: dict, *, desde: datetime, hasta: datetime, vendedor_uid: str | None,
    cliente_id: str | None, estado: str | None,
) -> list[dict[str, Any]]:
    if hasta <= desde:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "El rango de fechas no es valido")
    if hasta - desde > timedelta(days=MAX_RANGE_DAYS):
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, f"El rango no puede superar {MAX_RANGE_DAYS} dias")
    query = db.query(Evento).filter(Evento.inicio < hasta, Evento.fin > desde)
    if user["rol"] == "vendedor":
        vendedor_uid = user["uid"]
    if vendedor_uid:
        query = query.filter(Evento.vendedorUid == vendedor_uid)
    if cliente_id:
        query = query.filter(Evento.clienteId == cliente_id)
    if estado:
        query = query.filter(Evento.estado == estado)
    return _serialize_many(db, query.order_by(Evento.inicio, Evento.id).limit(MAX_RESULTS).all())


def create_evento(db: Session, payload, user: dict) -> dict[str, Any]:
    assert_cliente_visible(db, payload.clienteId, user)
    _check_opportunity(db, payload.oportunidadId, payload.clienteId)
    seller = user["uid"]
    if payload.vendedorUid and payload.vendedorUid != user["uid"]:
        if user["rol"] == "vendedor":
            raise _error(status.HTTP_403_FORBIDDEN, "Solo un supervisor puede agendar para otro vendedor")
        ensure_assignee_exists(db, payload.vendedorUid, "vendedorUid")
        seller = payload.vendedorUid
    data = payload.model_dump(exclude={"vendedorUid"})
    event = Evento(**data, vendedorUid=seller, estado="planificada")
    db.add(event)
    db.flush()
    if seller != user["uid"]:
        notificaciones.crear(
            db, seller, notificaciones.TIPO_VISITA, "Te agendaron una visita",
            mensaje=f"Agendada por {user.get('nombre') or 'un supervisor'}.",
            enlace="/calendario", referencia=f"{event.id}:agendada",
        )
    db.commit()
    return _serialize_many(db, [event])[0]


def update_evento(db: Session, event_id: str, payload, user: dict) -> dict[str, Any]:
    event = _get_editable(db, event_id, user)
    changes = payload.model_dump(exclude_unset=True)
    if event.estado != "planificada" and FROZEN_FIELDS & changes.keys():
        raise _error(status.HTTP_409_CONFLICT, f"Un evento {event.estado} ya no se puede mover ni cambiar de estado")
    for required in ("tipo", "inicio", "fin", "estado"):
        if required in changes and changes[required] is None:
            raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{required} no puede quedar vacio")
    start, end = changes.get("inicio", event.inicio), changes.get("fin", event.fin)
    if end <= start or end - start > timedelta(hours=12):
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "El fin debe ser posterior al inicio y durar hasta 12 horas")
    if "oportunidadId" in changes:
        _check_opportunity(db, changes["oportunidadId"], event.clienteId)

    previous_state = event.estado
    for key, value in changes.items():
        setattr(event, key, value)
    if previous_state == "planificada" and event.estado == "realizada":
        _register_interaction(db, event)
    db.commit()
    return _serialize_many(db, [event])[0]


def _register_interaction(db: Session, event: Evento) -> None:
    """La visita realizada queda en el historial del cliente (RF-02.04)."""
    detail = " · ".join(part for part in (event.lugar, event.notas) if part)
    interaction = Interaction(
        clienteId=event.clienteId, tipo=INTERACTION_TYPE[event.tipo], fecha=event.inicio,
        resumen=(f"Visita realizada. {detail}" if detail else "Visita realizada.")[:1000], vendedorUid=event.vendedorUid,
    )
    db.add(interaction)
    db.flush()
    event.interaccionId = interaction.id


# ── Avisos de visitas proximas (RQ-01) ───────────────────────────────────────

def sync_reminders(db: Session, now: datetime | None = None) -> int:
    """Avisa al dueno de las visitas que empiezan en menos de 24 h y en menos de 1 h (una vez cada vez)."""
    now = now or _now()
    upcoming = (
        db.query(Evento)
        .filter(Evento.estado == "planificada", Evento.inicio > now, Evento.inicio <= now + timedelta(hours=24))
        .all()
    )
    clientes = {c.id: c.empresa or c.nombre for c in db.query(Cliente.id, Cliente.empresa, Cliente.nombre).filter(
        Cliente.id.in_({e.clienteId for e in upcoming}))} if upcoming else {}
    created = 0
    for event in upcoming:
        key, label = ("1h", "en menos de 1 hora") if event.inicio - now <= timedelta(hours=1) else ("24h", "en menos de 24 horas")
        # La hora va en la referencia: si la visita se mueve, vuelve a avisar.
        if notificaciones.crear(
            db, event.vendedorUid, notificaciones.TIPO_VISITA,
            f"Visita {label}: {clientes.get(event.clienteId, 'cliente')}",
            mensaje=event.lugar, enlace="/calendario", referencia=f"{event.id}:{key}:{event.inicio.isoformat()}",
        ):
            created += 1
    db.commit()
    return created
