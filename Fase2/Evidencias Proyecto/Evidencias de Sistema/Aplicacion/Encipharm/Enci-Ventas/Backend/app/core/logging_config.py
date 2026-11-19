"""Logs estructurados (RNF-09): una linea JSON por evento, con hora ISO 8601 en UTC, nivel y peticion.

Los errores 5xx salen con nivel ERROR y el traceback: es lo que un filtro de alertas del hosting
(por ejemplo `level=ERROR`) necesita para avisar. No se registran cuerpos ni cabeceras de peticion.
"""
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone

from starlette.requests import Request

request_logger = logging.getLogger("app.request")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        data.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", fmt: str = "json") -> None:
    """Deja un solo manejador en la raiz (idempotente: se puede llamar mas de una vez)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def log_event(level: int, message: str, **fields) -> None:
    request_logger.log(level, message, extra={"extra_fields": fields})


class RequestLogMiddleware:
    """Un log por peticion (metodo, ruta, estado, duracion) y un X-Request-ID para seguirla entre logs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Request(scope).headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        started = time.perf_counter()
        status_code = 500

        async def send_with_id(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", request_id.encode()))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            route = scope.get("route")
            if scope["path"] != "/health":  # la sonda del hosting llega cada pocos segundos
                log_event(
                    logging.ERROR if status_code >= 500 else logging.INFO,
                    "request",
                    request_id=request_id, method=scope["method"], route=getattr(route, "path", scope["path"]),
                    status=status_code, duration_ms=round((time.perf_counter() - started) * 1000, 1),
                )
