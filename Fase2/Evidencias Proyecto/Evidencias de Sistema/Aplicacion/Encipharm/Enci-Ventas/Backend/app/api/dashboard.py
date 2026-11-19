from fastapi import APIRouter, Depends

from app.core.auth import require_role
from app.models.dashboard import DashboardResponse
from app.services.dashboard import build_dashboard
from app.core.db import get_db
from app.core.odm import Session


router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/vendedor", response_model=DashboardResponse)
async def get_dashboard_vendedor(
    user: dict = Depends(require_role("vendedor")),
    db: Session = Depends(get_db)
):
    return build_dashboard(db, vendedor_uid=user["uid"])


@router.get("/supervisor", response_model=DashboardResponse)
async def get_dashboard_supervisor(
    _: dict = Depends(require_role("supervisor")),
    db: Session = Depends(get_db)
):
    return build_dashboard(db)
