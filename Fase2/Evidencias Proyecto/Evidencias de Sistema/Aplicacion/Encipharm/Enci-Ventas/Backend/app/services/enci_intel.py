from urllib.parse import quote

import httpx
from fastapi import HTTPException
from app.core.config import get_settings

settings = get_settings()

# Intel puede estar dormido (hosting gratuito): se espera poco y se degrada con un mensaje claro.
INTEL_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MENSAJE_NO_DISPONIBLE = "Enci-Intel no esta disponible por ahora. El resto del CRM sigue funcionando."


class EnciIntelService:
    def __init__(self):
        self.base_url = settings.ENCI_INTEL_API_URL
        self.api_key = settings.ENCI_INTEL_API_KEY
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.api_key:
            self.headers["X-API-Key"] = self.api_key

    def _get_client(self):
        return httpx.AsyncClient(base_url=self.base_url or "", headers=self.headers, timeout=INTEL_TIMEOUT)

    async def _request(self, method: str, path: str, *, params: dict | None = None, json: dict | None = None):
        """Llama a Enci-Intel y traduce sus fallos a respuestas utiles para el cliente.

        - Sin URL configurada o sin red: 503 (el CRM sigue funcionando).
        - 404 y validaciones (400/422/429) se propagan tal cual.
        - Cualquier otro fallo, incluido un 401/403 por API key mala, es 502: un 401
          propagado haria que la web interprete la sesion del usuario como vencida.
        """
        if not self.base_url:
            raise HTTPException(status_code=503, detail="Enci-Intel no esta configurado (ENCI_INTEL_API_URL)")
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            async with self._get_client() as client:
                response = await client.request(method, path, params=clean_params or None, json=json)
        except httpx.HTTPError as error:
            raise HTTPException(status_code=503, detail=MENSAJE_NO_DISPONIBLE) from error

        status = response.status_code
        if status == 404:
            raise HTTPException(status_code=404, detail="No encontrado en Enci-Intel")
        if status in (400, 422, 429):
            raise HTTPException(status_code=status, detail="Enci-Intel rechazo la consulta")
        if status >= 400:
            raise HTTPException(status_code=502, detail="Enci-Intel respondio con un error")
        return response.json()

    async def get_noticias(self):
        data = await self._request("GET", "/api/v1/market/news")
        # Traduce el esquema de Enci-Intel (empresa/titulo/fecha/resumen)
        # al que espera el frontend de Enci-Ventas (source/title/date/body/tags).
        if isinstance(data, list):
            return [
                {
                    **item,
                    "source": item.get("empresa"),
                    "title": item.get("titulo"),
                    "date": item.get("fecha"),
                    "body": item.get("resumen"),
                    "tags": item.get("tags", []),
                }
                for item in data
            ]
        return data

    async def get_competencia(self):
        positioning = await self._request("GET", "/api/v1/market/positioning-matrix")
        share = await self._request("GET", "/api/v1/market/share")
        return {
            "positioning_matrix": positioning,
            "share": share,
        }

    async def chat_query(self, pregunta: str):
        return await self._request("POST", "/api/v1/chat/query", json={"question": pregunta})

    async def get_llm_settings(self):
        return await self._request("GET", "/api/v1/admin/llm/runtime")

    async def get_alertas(self, *, priority=None, type=None, competitor=None, limit=50, offset=0):
        return await self._request(
            "GET", "/api/v1/alerts/",
            params={"priority": priority, "type": type, "competitor": competitor, "limit": limit, "offset": offset},
        )

    async def get_alerta(self, alert_id: str):
        return await self._request("GET", f"/api/v1/alerts/{quote(alert_id, safe='')}")

    async def search_productos(self, *, q="", estado=None, limit=20, offset=0):
        return await self._request(
            "GET", "/api/v1/sag/productos",
            params={"q": q or None, "estado": estado, "limit": limit, "offset": offset},
        )

    async def get_producto(self, registro: str):
        return await self._request("GET", f"/api/v1/sag/productos/{quote(registro, safe='')}")
