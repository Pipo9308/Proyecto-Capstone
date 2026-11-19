"""Auditoria (RNF-03): un registro por cada accion que cambia datos y por cada descarga de archivo.

Se alimenta desde un middleware (no se toca cada servicio): guarda quien (uid y rol del token),
que (metodo y ruta), sobre que recurso, cuando, desde donde (IP, navegador/app) y como termino.
Nunca guarda cuerpos de peticion ni cabeceras: ahi viajan contrasenas y tokens.
"""
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

import jwt
from app.core.odm import Session

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.models_sql.audit import AuditLog

logger = logging.getLogger(__name__)

AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
# GET que si se auditan: abrir un archivo con enlace firmado.
AUDITED_GET_PREFIXES = ("/propuestas/archivos/descarga",)
# Alto volumen y poco valor: marcar avisos como leidos y preguntas al chat (su uso ya se cuenta aparte).
SKIPPED_PREFIXES = ("/notificaciones", "/inteligencia/alertas", "/inteligencia/competencia-chat", "/rag/chat")


def should_audit(method: str, path: str) -> bool:
    if path.startswith(SKIPPED_PREFIXES):
        return False
    return method in AUDITED_METHODS or (method == "GET" and path.startswith(AUDITED_GET_PREFIXES))


def result_of(status_code: int) -> str:
    if status_code < 400:
        return "success"
    if status_code in (401, 403):
        return "denied"
    return "error" if status_code >= 500 else "failure"


def client_ip(request) -> str | None:
    """IP de origen. Detras de un proxy (Render) llega en X-Forwarded-For; es informativa, no una barrera."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64] or None
    return request.client.host if request.client else None


def token_identity(request) -> tuple[str | None, str | None]:
    """(uid, rol) del token de la peticion, o (None, None) si no hay uno valido."""
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None, None
    try:
        payload = jwt.decode(header[7:], get_settings().JWT_SECRET, algorithms=[ALGORITHM])
    except Exception:
        return None, None
    return payload.get("uid"), payload.get("rol")


def annotate(request, *, user=None, **details) -> None:
    """Un endpoint agrega datos al registro de su peticion (p. ej. el correo de un intento de login)."""
    if user is not None:
        request.state.audit_user = (user.id, user.rol)
    if details:
        request.state.audit_details = {**getattr(request.state, "audit_details", {}), **details}


def build_event(request, status_code: int) -> AuditLog:
    route = request.scope.get("route")
    template = getattr(route, "path", None) or request.url.path
    params = request.scope.get("path_params") or {}
    uid, role = getattr(request.state, "audit_user", None) or token_identity(request)
    segments = [s for s in template.split("/") if s and not s.startswith("{")]
    return AuditLog(
        createdAt=datetime.now(timezone.utc), userUid=uid, userRole=role, method=request.method, route=template[:200],
        resource=(segments[0] if segments else "/")[:60],
        resourceId=str(next(iter(params.values())))[:120] if params else None,
        statusCode=status_code, result=result_of(status_code), ip=client_ip(request),
        userAgent=(request.headers.get("user-agent") or "")[:300] or None,
        client=(request.headers.get("x-enci-client") or "")[:10] or None,
        details=getattr(request.state, "audit_details", None),
    )


def write_event(session_factory: Callable[[], Session], event: AuditLog) -> None:
    """Inserta el registro. Un fallo de auditoria se registra en el log pero no tumba la peticion."""
    try:
        with session_factory() as db:
            db.add(event)
            db.commit()
    except Exception:
        logger.exception("No se pudo guardar el registro de auditoria (%s %s)", event.method, event.route)


def iso_ms(moment: datetime) -> str:
    """ISO 8601 en UTC con milisegundos: 2026-10-13T20:00:00.123Z."""
    return moment.replace(tzinfo=None).isoformat(timespec="milliseconds") + "Z"


def serialize(row: AuditLog) -> dict[str, Any]:
    return {
        "id": row.id, "timestamp": iso_ms(row.createdAt), "userUid": row.userUid, "userRole": row.userRole,
        "method": row.method, "route": row.route, "resource": row.resource, "resourceId": row.resourceId,
        "statusCode": row.statusCode, "result": row.result, "ip": row.ip, "userAgent": row.userAgent,
        "client": row.client, "details": row.details,
    }


def list_events(
    db: Session, *, desde: datetime | None, hasta: datetime | None, user_uid: str | None, resource: str | None,
    result: str | None, limit: int, offset: int,
) -> dict[str, Any]:
    query = db.query(AuditLog)
    if desde:
        query = query.filter(AuditLog.createdAt >= desde)
    if hasta:
        query = query.filter(AuditLog.createdAt < hasta)
    if user_uid:
        query = query.filter(AuditLog.userUid == user_uid)
    if resource:
        query = query.filter(AuditLog.resource == resource)
    if result:
        query = query.filter(AuditLog.result == result)
    total = query.count()
    rows = query.order_by(AuditLog.createdAt.desc(), AuditLog.id).offset(offset).limit(limit).all()
    return {"items": [serialize(r) for r in rows], "total": total}
