from fastapi import APIRouter, Depends
from app.api.mongo_service import get_dashboard_summary as _get_summary
from app.api.auth import require_auth

router = APIRouter()

@router.get("/summary")
async def dashboard_summary(_: dict = Depends(require_auth)):
    return await _get_summary()