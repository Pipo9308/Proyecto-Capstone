"""Consulta del registro de auditoria (solo admin, solo lectura)."""
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from app.core.odm import Session

from app.core.auth import require_role
from app.core.db import get_db
from app.services import audit

router = APIRouter(prefix="/auditoria", tags=["Auditoria"])


class AuditEntry(BaseModel):
    id: str
    timestamp: str  # ISO 8601 UTC con milisegundos
    userUid: str | None = None
    userRole: str | None = None
    method: str
    route: str
    resource: str
    resourceId: str | None = None
    statusCode: int
    result: str
    ip: str | None = None
    userAgent: str | None = None
    client: str | None = None
    details: dict[str, Any] | None = None


class AuditPage(BaseModel):
    items: list[AuditEntry]
    total: int


def _utc(value: datetime | None) -> datetime | None:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value


@router.get("", response_model=AuditPage)
async def get_auditoria(
    desde: datetime | None = None,
    hasta: datetime | None = None,
    usuario: str | None = Query(default=None, max_length=36),
    recurso: str | None = Query(default=None, max_length=60),
    resultado: Literal["success", "denied", "failure", "error"] | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: dict = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    return audit.list_events(
        db, desde=_utc(desde), hasta=_utc(hasta), user_uid=usuario, resource=recurso, result=resultado,
        limit=limit, offset=offset,
    )
