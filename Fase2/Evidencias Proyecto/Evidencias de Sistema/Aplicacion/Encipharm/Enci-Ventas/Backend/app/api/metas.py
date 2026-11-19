"""Metas mensuales de ventas por vendedor: las fija el supervisor y el dashboard mide contra ellas."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import require_role
from app.core.db import get_db
from app.core.odm import Session
from app.models_sql.meta import MetaVenta
from app.models_sql.user import User

router = APIRouter(prefix="/metas", tags=["Metas"])
MES = r"^\d{4}-(0[1-9]|1[0-2])$"


class MetaIn(BaseModel):
    vendedorUid: str = Field(max_length=36)
    mes: str = Field(pattern=MES)
    monto: float = Field(ge=0, le=100_000_000_000)


class MetaOut(BaseModel):
    vendedorUid: str
    mes: str
    monto: float


@router.get("", response_model=list[MetaOut])
async def get_metas(
    mes: str = Query(pattern=MES),
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db),
):
    """El vendedor ve solo su meta; supervisor y admin ven la de todo el equipo."""
    rows = db.query(MetaVenta).filter(MetaVenta.mes == mes).all()
    if user.get("rol") not in ("supervisor", "admin"):
        rows = [r for r in rows if r.vendedorUid == user["uid"]]
    return [MetaOut(vendedorUid=r.vendedorUid, mes=r.mes, monto=r.monto) for r in rows]


@router.put("", response_model=MetaOut)
async def put_meta(
    payload: MetaIn,
    user: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db),
):
    if db.get(User, payload.vendedorUid) is None:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    meta_id = f"{payload.vendedorUid}:{payload.mes}"
    row = db.get(MetaVenta, meta_id) or MetaVenta(id=meta_id, vendedorUid=payload.vendedorUid, mes=payload.mes)
    row.monto = payload.monto
    row.fijadaPor = user["uid"]
    row.updatedAt = datetime.now(timezone.utc)
    db.add(row)
    db.commit()
    return MetaOut(vendedorUid=row.vendedorUid, mes=row.mes, monto=row.monto)
