"""Busqueda web en vivo para el chat de competencia (apagada por defecto).

Dos precauciones, ambas exigidas por el ERS (RF-08.09 y RNF-10):
- Lo que se envia al buscador no lleva datos personales (correos, telefonos, RUT).
- Lo que vuelve es contenido NO confiable: el modelo recibe el texto marcado como tal
  y nunca debe obedecer instrucciones que aparezcan dentro.
"""
import re
from dataclasses import dataclass
from typing import Protocol

import httpx

TAVILY_URL = "https://api.tavily.com/search"
WEB_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
MAX_QUERY_CHARS = 200
MAX_SNIPPET_CHARS = 400

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b")
_PHONE = re.compile(r"(?<!\d)(?:\+?56[\s-]?)?9[\s-]?\d{4}[\s-]?\d{4}(?!\d)")


def scrub_pii(text: str) -> str:
    """Quita correos, RUT y telefonos chilenos antes de enviar texto a un tercero."""
    cleaned = _EMAIL.sub("", text or "")
    cleaned = _RUT.sub("", cleaned)
    cleaned = _PHONE.sub("", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


@dataclass
class WebResult:
    title: str
    url: str
    snippet: str
    date: str | None = None


class WebSearch(Protocol):
    async def search(self, query: str) -> list[WebResult]: ...


class WebSearchError(Exception):
    """El buscador no respondio o respondio con error: el chat sigue sin web."""


class TavilySearch:
    def __init__(self, api_key: str, max_results: int = 5, transport: httpx.AsyncBaseTransport | None = None):
        self._api_key = api_key
        self._max_results = max_results
        self._transport = transport

    async def search(self, query: str) -> list[WebResult]:
        safe_query = scrub_pii(query)[:MAX_QUERY_CHARS]
        if not safe_query:
            return []
        try:
            async with httpx.AsyncClient(timeout=WEB_TIMEOUT, transport=self._transport) as client:
                response = await client.post(
                    TAVILY_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={"query": safe_query, "max_results": self._max_results, "search_depth": "basic"},
                )
            response.raise_for_status()
            items = response.json().get("results", [])
        except (httpx.HTTPError, ValueError) as error:
            raise WebSearchError("La busqueda web no esta disponible.") from error
        return [
            WebResult(
                title=str(item.get("title") or item.get("url") or "Sin titulo"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or "")[:MAX_SNIPPET_CHARS],
                date=item.get("published_date"),
            )
            for item in items[: self._max_results]
            if item.get("url")
        ]
