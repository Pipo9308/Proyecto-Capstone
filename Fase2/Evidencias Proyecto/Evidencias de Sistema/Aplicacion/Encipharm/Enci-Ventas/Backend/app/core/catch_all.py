from starlette.requests import Request

from app.core.errors import unhandled_exception_handler


class CatchAllErrorsMiddleware:
    """Convierte un error no controlado en el 500 JSON de siempre, dentro de CORS.

    Starlette responde los errores no controlados desde su capa mas externa, por fuera del CORS: el
    navegador recibia un 500 sin cabeceras CORS y lo mostraba como "bloqueado por CORS", ocultando
    la causa real. Aqui el 500 sale con las cabeceras CORS y el error queda registrado.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:  # ya se empezo a responder: no se puede cambiar el estado
                raise
            response = await unhandled_exception_handler(Request(scope), exc)
            await response(scope, receive, send)
