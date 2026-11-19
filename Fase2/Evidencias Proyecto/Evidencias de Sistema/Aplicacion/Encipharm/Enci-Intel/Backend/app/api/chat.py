import json
import logging
import os
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.rag import engine
from app.api.rate_limiter import check_and_increment
from app.api.auth import INTEL_SERVICE_API_KEY, rechazar_pendiente

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    species: str | None = None
    history: list[dict] | None = None
    language: str | None = "es"


def get_chat_user(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> dict:
    if x_api_key is not None:
        if not INTEL_SERVICE_API_KEY or x_api_key != INTEL_SERVICE_API_KEY:
            raise HTTPException(status_code=401, detail="API key de servicio invalida")
        return {"uid": "service-enci-ventas"}
    if authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "")
        try:
            import jwt
            from app.api.auth import SECRET_KEY, ALGORITHM
            decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except Exception:
            raise HTTPException(status_code=401, detail="Token inválido")
        rechazar_pendiente(decoded)
        return {"uid": decoded["sub"], "email": decoded.get("email", "")}
    if os.environ.get("CHAT_AUTH_REQUIRED", "true").lower() != "false":
        raise HTTPException(status_code=401, detail="Token no enviado")
    ip = request.client.host if request.client else "unknown"
    return {"uid": f"guest-{ip}"}


@router.post("/stream")
def chat_stream(
    req: ChatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    user = get_chat_user(request, authorization, x_api_key)
    if not check_and_increment(user["uid"]):
        raise HTTPException(status_code=429, detail="Límite diario de consultas alcanzado.")

    def safe_stream():
        try:
            for chunk in engine.query_stream(req.question, req.species, req.history, req.language):
                yield chunk
        except Exception as error:  # el detalle va al log, no al usuario
            logger.error("Fallo el Consultor Vet: %s: %s", type(error).__name__, str(error)[:300])
            yield f"data: {json.dumps({'error': 'Error procesando la consulta.'})}\n\n"

    return StreamingResponse(safe_stream(), media_type="text/event-stream")


@router.post("/query")
def chat_query(
    req: ChatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
):
    user = get_chat_user(request, authorization, x_api_key)
    if not check_and_increment(user["uid"]):
        raise HTTPException(status_code=429, detail="Límite diario de consultas alcanzado.")
    result = engine.query(req.question, req.species, req.history)
    return {"success": True, "data": result}


@router.get("/docs-count")
def docs_count(request: Request, authorization: str | None = Header(default=None), x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    get_chat_user(request, authorization, x_api_key)
    if not engine._store:
        return {"success": True, "data": {"documents": 0}}
    return {"success": True, "data": {"documents": len(engine._store.chunk_count_by_filename())}}
