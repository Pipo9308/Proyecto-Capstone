from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.auth import router as auth_router
from app.api.clientes import router as clientes_router
from app.api.comercial import router as comercial_router
from app.api.metas import router as metas_router
from app.api.dashboard import router as dashboard_router
from app.api.inteligencia import router as inteligencia_router
from app.api.competencia_chat import router as competencia_chat_router
from app.api.competencia_productos import router as competencia_productos_router
from app.api.notificaciones import router as notificaciones_router
from app.api.eventos import router as eventos_router
from app.api.propuesta_archivos import router as propuesta_archivos_router
from app.api.rag import router as rag_router
from app.api.users import router as users_router
from app.api.auditoria import router as auditoria_router
from app.core.auth import get_current_user, require_role
from app.core.config import get_settings
from app.core.audit_middleware import AuditMiddleware
from app.core.catch_all import CatchAllErrorsMiddleware
from app.core.db import SessionLocal
from app.core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.headers import apply_dynamic_cache_headers
from app.core.logging_config import RequestLogMiddleware, configure_logging
from app.core.rate_limit import RequestSizeLimitMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.core.readiness import ReadinessReport, build_readiness_report
settings = get_settings()
configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url=None if settings.APP_ENV == "production" else "/docs",
    openapi_url=None if settings.APP_ENV == "production" else "/openapi.json",
    redoc_url=None,
)

limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"], storage_uri=settings.REDIS_URL)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=1_000_000, path_limits={
    "/rag/documents/upload": settings.RAG_MAX_UPLOAD_BYTES,
    # PDF adjuntos de propuesta: el limite del archivo mas 1 MB de margen para el multipart.
    "/propuestas/*/archivos": settings.PROPUESTA_MAX_ARCHIVO_BYTES + 1_000_000,
})
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Va antes que CORS (queda por dentro) para que los 500 lleven las cabeceras CORS.
app.add_middleware(CatchAllErrorsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Enci-Client"],
)


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    apply_dynamic_cache_headers(request.url.path, response.headers)
    if request.url.path.startswith("/docs"):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self' https://unpkg.com https://www.gstatic.com; "
            "script-src 'self' 'unsafe-inline' https://unpkg.com https://www.gstatic.com; "
            "style-src 'self' 'unsafe-inline' https://unpkg.com; "
            "frame-ancestors 'none'",
        )
    else:
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
    return response

# La fabrica se lee en cada peticion para poder reemplazarla en los tests.
app.state.audit_session_factory = SessionLocal
app.add_middleware(AuditMiddleware, session_factory_getter=lambda: app.state.audit_session_factory)
# El ultimo que se agrega es el mas externo: ve toda la peticion, incluida la respuesta de error.
app.add_middleware(RequestLogMiddleware)

app.include_router(auth_router)
app.include_router(clientes_router)
app.include_router(comercial_router)
app.include_router(metas_router)
app.include_router(dashboard_router)
app.include_router(inteligencia_router)
app.include_router(competencia_chat_router)
app.include_router(competencia_productos_router)
app.include_router(notificaciones_router)
app.include_router(eventos_router)
app.include_router(propuesta_archivos_router)
app.include_router(rag_router)
app.include_router(users_router)
app.include_router(auditoria_router)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/readiness", response_model=ReadinessReport)
def readiness(_: dict = Depends(require_role("admin"))):
    """Revision de configuracion para el go-live: muestra que falta configurar, asi que solo la ve un admin."""
    return build_readiness_report(settings)


@app.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "uid": user.get("uid"),
        "email": user.get("email"),
        "rol": user.get("rol"),
        "activo": user.get("activo", True),
        "message": "Token valido",
    }
