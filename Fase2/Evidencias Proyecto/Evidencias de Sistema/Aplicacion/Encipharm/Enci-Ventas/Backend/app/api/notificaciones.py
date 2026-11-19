"""RQ-01: avisos dentro de la web. Cada usuario ve y marca solo los suyos."""
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from app.core.odm import Session

from app.core.auth import require_role
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, get_db
from app.services import notificaciones as service
from app.services.enci_intel import EnciIntelService

router = APIRouter(prefix="/notificaciones", tags=["Notificaciones"])

NOTIFICATION_ID = Path(max_length=36, pattern=r"^[A-Za-z0-9\-]+$")


class NotificacionResponse(BaseModel):
    id: str
    tipo: str
    titulo: str
    mensaje: str | None = None
    enlace: str | None = None
    leida: bool
    createdAt: datetime


class NotificacionesPagina(BaseModel):
    items: list[NotificacionResponse]
    total: int
    noLeidas: int


# Dependencias reemplazables en los tests ────────────────────────────────────

def get_session_factory():
    return SessionLocal


def get_intel() -> EnciIntelService:
    return EnciIntelService()


@router.get("", response_model=NotificacionesPagina)
async def get_notificaciones(
    background: BackgroundTasks,
    soloNoLeidas: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    factory=Depends(get_session_factory),
    intel: EnciIntelService = Depends(get_intel),
):
    """Lista los avisos del usuario. De paso, pone al dia los de Intel (en segundo plano, con tope de frecuencia)."""
    page = service.listar(db, user["uid"], solo_no_leidas=soloNoLeidas, limit=limit, offset=offset)
    background.add_task(
        service.mantenimiento, factory, intel,
        poll_seconds=settings.NOTIFICATIONS_INTEL_POLL_SECONDS,
        lookback_hours=settings.NOTIFICATIONS_INTEL_LOOKBACK_HOURS,
    )
    return page


@router.patch("/{notification_id}/leida", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(
    notification_id: str = NOTIFICATION_ID, user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db),
):
    if not service.marcar_leida(db, user["uid"], notification_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notificacion no encontrada")


@router.post("/marcar-todas")
async def mark_all_read(user: dict = Depends(require_role("vendedor")), db: Session = Depends(get_db)):
    return {"marcadas": service.marcar_todas(db, user["uid"])}
