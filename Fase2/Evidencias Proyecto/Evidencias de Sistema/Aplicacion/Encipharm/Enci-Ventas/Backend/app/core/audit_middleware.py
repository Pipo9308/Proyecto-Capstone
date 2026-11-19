from starlette.requests import Request

from app.services import audit


class AuditMiddleware:
    """Registra la auditoria justo cuando la respuesta empieza a enviarse (ya se sabe como termino).

    Es un middleware ASGI puro (no BaseHTTPMiddleware) a proposito: asi el registro se guarda
    antes de que corran las tareas en segundo plano de la peticion, sin competir con ellas.
    """

    def __init__(self, app, session_factory_getter):
        self.app = app
        self.session_factory_getter = session_factory_getter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not audit.should_audit(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return

        recorded = False

        def record(status_code: int) -> None:
            nonlocal recorded
            if not recorded:
                recorded = True
                audit.write_event(self.session_factory_getter(), audit.build_event(Request(scope), status_code))

        async def send_and_record(message):
            if message["type"] == "http.response.start":
                record(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, send_and_record)
        except Exception:
            record(500)
            raise
