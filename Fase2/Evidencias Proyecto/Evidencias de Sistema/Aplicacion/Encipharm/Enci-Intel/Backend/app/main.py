import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv(override=True)

from app.api import dashboard, alerts, agents, products, market, chat, admin_documents, admin_users, auth, sag, llm_settings  # noqa: E402
from app.rag import engine  # noqa: E402
from app.llm_settings import load as load_llm_settings  # noqa: E402
from app.db import connect_to_db, close_db_connection, get_db
from app.scheduler import preparar_agentes, start_scheduler, shutdown_scheduler

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    connect_to_db()
    await load_llm_settings()
    await engine.startup()
    start_scheduler()
    try:
        await preparar_agentes(get_db())
    except Exception:  # sin agentes programados la API igual debe arrancar
        logger.exception("No se pudieron preparar los agentes al arrancar")
    yield
    shutdown_scheduler()
    close_db_connection()


app = FastAPI(title="Enci-Intel API", version="1.0.0", lifespan=lifespan)

# INTEL_CORS_ORIGINS: origenes extra separados por coma (ej. la URL de Vercel
# del deploy actual). Los localhost de siempre quedan fijos para dev local;
# lo variable por entorno se agrega encima, sin tocar codigo en cada deploy.
_extra_origins = [
    o.strip().rstrip("/")
    for o in os.environ.get("INTEL_CORS_ORIGINS", "").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        *_extra_origins,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,            prefix="/api/v1/auth",            tags=["Auth"])
app.include_router(dashboard.router,       prefix="/api/v1/dashboard",       tags=["Dashboard"])
app.include_router(alerts.router,          prefix="/api/v1/alerts",          tags=["Alerts"])
app.include_router(agents.router,          prefix="/api/v1/agents",          tags=["Agents"])
app.include_router(products.router,        prefix="/api/v1/products",        tags=["Products"])
app.include_router(market.router,          prefix="/api/v1/market",          tags=["Market"])
app.include_router(sag.router,             prefix="/api/v1/sag",             tags=["SAG"])
app.include_router(chat.router,            prefix="/api/v1/chat",            tags=["Chat"])
app.include_router(admin_documents.router, prefix="/api/v1/admin/documents", tags=["Admin Documents"])
app.include_router(admin_users.router,     prefix="/api/v1/admin/users",     tags=["Admin Users"])
app.include_router(llm_settings.router,    prefix="/api/v1/admin/llm",       tags=["Admin LLM"])


@app.get("/health")
def health():
    return {"success": True, "status": "ok"}


@app.get("/")
def root():
    return {"message": "Enci-Intel Backend funcionando"}
