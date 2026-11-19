from fastapi import APIRouter, Depends
from app.db import get_db
from app.api.auth import require_user_or_service

router = APIRouter()

@router.get("/share")
async def get_market_share(_: dict = Depends(require_user_or_service)):
    db = get_db()
    
    data = await db.market_share.find_one({}, sort=[("period", -1)])
    if not data:
        return {
            "success": True,
            "data": {
                "period": "Q1-2026",
                "total_market_usd": 0,
                "competitors": []
            }
        }
    
    data.pop("_id", None)
    return {"success": True, "data": data}


@router.get("/import-trends")
async def get_import_trends(_: dict = Depends(require_user_or_service)):
    db = get_db()
    
    data = await db.import_trends.find_one({}, sort=[("last_updated", -1)])
    if not data:
        return {
            "success": True,
            "data": {
                "months": [],
                "series": [],
                "source": "SAG_DIN",
                "last_updated": ""
            }
        }
    
    data.pop("_id", None)
    return {"success": True, "data": data}


@router.get("/positioning-matrix")
async def get_positioning_matrix(_: dict = Depends(require_user_or_service)):
    db = get_db()

    data = await db.positioning_matrix.find_one({}, sort=[("last_updated", -1)])
    if not data:
        return {
            "success": True,
            "data": {
                "axes": {
                    "x": {"label": "Velocidad Regulatoria ISP", "unit": "días promedio"},
                    "y": {"label": "Precio Promedio de Portafolio", "unit": "CLP"}
                },
                "points": []
            }
        }

    data.pop("_id", None)
    return {"success": True, "data": data}


@router.get("/news")
async def get_competitor_news(_: dict = Depends(require_user_or_service)):
    """Noticias de competencia scrapeadas por agent-competidores
    (coleccion competitor_news). Consumido por el proxy de Enci-Ventas."""
    db = get_db()
    docs = await db.competitor_news.find().sort("updated_at", -1).limit(100).to_list(length=100)
    docs = [d for d in docs if d.get("relevante") is not False]  # el agente marca las que el modelo descarto
    for doc in docs:
        doc.pop("_id", None)
    return docs