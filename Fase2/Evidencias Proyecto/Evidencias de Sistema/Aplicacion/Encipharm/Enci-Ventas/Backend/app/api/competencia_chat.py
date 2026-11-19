import json
from typing import Literal

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from app.core.odm import Session

from app.core.auth import require_intel_access, require_role
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, get_db
from app.services import competencia_chat as chat
from app.services.competencia_llm import LlmClient, build_llm_client
from app.services.llm_runtime import llm_overrides
from app.services.enci_intel import EnciIntelService
from app.services.web_search import TavilySearch, WebSearch

router = APIRouter(
    prefix="/inteligencia/competencia-chat",
    tags=["Chat de competencia"],
    dependencies=[Depends(require_intel_access)],
)

CONVERSATION_ID = Path(max_length=36, pattern=r"^[A-Za-z0-9\-]+$")


class ChatRequest(BaseModel):
    pregunta: str = Field(max_length=1000)
    conversacion_id: str | None = Field(default=None, max_length=36)

    @field_validator("pregunta")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("La pregunta no puede estar vacia")
        return value


class FeedbackRequest(BaseModel):
    valor: Literal["up", "down"] | None


# Dependencias reemplazables en los tests ────────────────────────────────────

def get_chat_settings() -> Settings:
    return get_settings()


def get_session_factory():
    return SessionLocal


async def get_llm(settings: Settings = Depends(get_chat_settings)) -> LlmClient:
    return build_llm_client(settings.model_copy(update=await llm_overrides()))


def get_intel() -> EnciIntelService:
    return EnciIntelService()


def get_web(settings: Settings = Depends(get_chat_settings)) -> WebSearch | None:
    if settings.WEB_SEARCH_ENABLED and settings.TAVILY_API_KEY:
        return TavilySearch(settings.TAVILY_API_KEY, max_results=settings.WEB_SEARCH_MAX_RESULTS)
    return None


def _prepare(factory, user: dict, request: ChatRequest, settings: Settings) -> list[dict]:
    """Valida la conversacion (404) y cuenta la pregunta contra el tope diario (429)."""
    with factory() as db:
        history = chat.load_history(db, user["uid"], request.conversacion_id)
        chat.consume_quota(db, user["uid"], settings.COMPETENCIA_CHAT_DAILY_LIMIT)
    return history


def _events(request, user, history, factory, llm, intel, web, settings):
    return chat.answer_question(
        session_factory=factory, user_id=user["uid"], question=request.pregunta,
        conversation_id=request.conversacion_id, history=history, llm=llm, intel=intel, web=web, settings=settings,
    )


@router.post("")
async def ask(
    request: ChatRequest,
    user: dict = Depends(require_intel_access),
    settings: Settings = Depends(get_chat_settings),
    factory=Depends(get_session_factory),
    llm: LlmClient = Depends(get_llm),
    intel: EnciIntelService = Depends(get_intel),
    web: WebSearch | None = Depends(get_web),
):
    """Respuesta completa (sin streaming)."""
    from fastapi import HTTPException

    history = _prepare(factory, user, request, settings)
    text, sources, end = [], [], {}
    async for event in _events(request, user, history, factory, llm, intel, web, settings):
        if event["tipo"] == "error":
            raise HTTPException(
                status_code=event["estado"], detail={"codigo": event["codigo"], "error": event["mensaje"], "detalles": {}}
            )
        if event["tipo"] == "texto":
            text.append(event["texto"])
        elif event["tipo"] == "fuentes":
            sources = event["fuentes"]
        elif event["tipo"] == "fin":
            end = event
    return {"respuesta": "".join(text), "fuentes": sources, **{k: v for k, v in end.items() if k != "tipo"}}


@router.post("/stream")
async def ask_stream(
    request: ChatRequest,
    user: dict = Depends(require_intel_access),
    settings: Settings = Depends(get_chat_settings),
    factory=Depends(get_session_factory),
    llm: LlmClient = Depends(get_llm),
    intel: EnciIntelService = Depends(get_intel),
    web: WebSearch | None = Depends(get_web),
):
    """Respuesta por eventos SSE: estado, fuentes, texto (varios) y fin; o error."""
    history = _prepare(factory, user, request, settings)

    async def stream():
        async for event in _events(request, user, history, factory, llm, intel, web, settings):
            yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@router.get("/uso")
def usage(
    user: dict = Depends(require_intel_access),
    settings: Settings = Depends(get_chat_settings),
    db: Session = Depends(get_db),
):
    return chat.get_usage(db, user["uid"], settings.COMPETENCIA_CHAT_DAILY_LIMIT)


@router.get("/conversaciones")
def list_conversations(
    limit: int = Query(50, ge=1, le=100), user: dict = Depends(require_intel_access), db: Session = Depends(get_db)
):
    return chat.list_conversations(db, user["uid"], limit)


@router.get("/conversaciones/{conversation_id}")
def get_conversation(
    conversation_id: str = CONVERSATION_ID, user: dict = Depends(require_intel_access), db: Session = Depends(get_db)
):
    return chat.get_conversation(db, user["uid"], conversation_id)


@router.delete("/conversaciones/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str = CONVERSATION_ID, user: dict = Depends(require_intel_access), db: Session = Depends(get_db)
):
    chat.delete_conversation(db, user["uid"], conversation_id)


@router.patch("/conversaciones/{conversation_id}/mensajes/{indice}/feedback")
def feedback(
    body: FeedbackRequest,
    conversation_id: str = CONVERSATION_ID,
    indice: int = Path(ge=0, le=10_000),
    user: dict = Depends(require_intel_access),
    db: Session = Depends(get_db),
):
    chat.set_feedback(db, user["uid"], conversation_id, indice, body.valor)
    return {"conversacion_id": conversation_id, "mensaje_indice": indice, "feedback": body.valor}


@router.get("/reporte")
def report(
    mes: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    _: dict = Depends(require_role("admin")),
    settings: Settings = Depends(get_chat_settings),
    db: Session = Depends(get_db),
):
    """Uso y costo aproximado del mes por usuario (solo admin)."""
    return chat.monthly_report(db, mes, settings)
