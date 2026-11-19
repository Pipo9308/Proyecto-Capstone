from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.db import get_db
from app.api.auth import require_auth

router = APIRouter()


class RecommendationRequest(BaseModel):
    question: str
    species: str | None = None


@router.post("/recommendations")
async def get_recommendations(req: RecommendationRequest, _: dict = Depends(require_auth)):
    return {"success": True, "data": {"encipharm": [], "competencia": []}}

@router.get("/")
async def get_products(_: dict = Depends(require_auth)):
    db = get_db()
    docs = await db.products.find({}).to_list(length=100)
    for doc in docs:
        doc["id"] = str(doc.pop("_id", ""))
        
    return {
        "success": True,
        "data": docs
    }


@router.get("/{product_id}")
async def get_product_detail(product_id: str, _: dict = Depends(require_auth)):
    db = get_db()
    query = {"_id": product_id}
    doc = await db.products.find_one(query)
    if not doc:
        doc = await db.products.find_one({"id": product_id})
        if not doc:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
            
    doc["id"] = str(doc.pop("_id", ""))
    
    return {
        "success": True,
        "data": doc
    }