"""RQ-02: calendario interno. El vendedor gestiona sus eventos; supervisor y admin ven todos."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query, status
from app.core.odm import Session

from app.core.auth import require_role
from app.core.db import get_db
from app.models.evento import EstadoEvento, EventoCreate, EventoResponse, EventoUpdate
from app.services import eventos as service

router = APIRouter(prefix="/eventos", tags=["Calendario"])

EVENT_ID = Path(max_length=36, pattern=r"^[A-Za-z0-9\-]+$")


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


@router.get("", response_model=list[EventoResponse])
async def get_eventos(
    desde: datetime,
    hasta: datetime,
    vendedorUid: str | None = Query(default=None, max_length=36),
    clienteId: str | None = Query(default=None, max_length=36),
    estado: EstadoEvento | None = None,
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db),
):
    """Eventos que se cruzan con [desde, hasta). Un vendedor solo recibe los suyos."""
    return service.list_eventos(
        db, user, desde=_utc(desde), hasta=_utc(hasta), vendedor_uid=vendedorUid, cliente_id=clienteId, estado=estado,
    )


@router.post("", response_model=EventoResponse, status_code=status.HTTP_201_CREATED)
async def post_evento(payload: EventoCreate, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db)):
    return service.create_evento(db, payload, user)


@router.patch("/{event_id}", response_model=EventoResponse)
async def patch_evento(
    payload: EventoUpdate, event_id: str = EVENT_ID, user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db),
):
    """Edita, mueve, marca como realizada (queda en el historial del cliente) o cancela."""
    return service.update_evento(db, event_id, payload, user)
