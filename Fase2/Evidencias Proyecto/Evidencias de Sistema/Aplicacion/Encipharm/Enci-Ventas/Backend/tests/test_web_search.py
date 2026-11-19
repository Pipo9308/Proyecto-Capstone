import json

import httpx
import pytest

from app.services.web_search import TavilySearch, WebSearchError, scrub_pii


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("precio de Draxxin contacto juan.perez@empresa.cl", "precio de Draxxin contacto"),
        ("cliente RUT 12.345.678-5 compra", "cliente RUT compra"),
        ("llamar al +56 9 8765 4321 por Zoetis", "llamar al por Zoetis"),
        ("telefono 912345678 Agrovet", "telefono Agrovet"),
        ("noticias de Zoetis Chile 2026", "noticias de Zoetis Chile 2026"),
    ],
)
def test_scrub_pii(raw, expected):
    assert scrub_pii(raw) == expected


def _search(handler):
    return TavilySearch("clave-tavily", max_results=3, transport=httpx.MockTransport(handler))


@pytest.mark.anyio
async def test_search_sends_a_clean_query_with_bearer_auth_and_parses_results():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"results": [
            {"title": "Zoetis Chile", "url": "https://diario.cl/z", "content": "x" * 1000, "published_date": "2026-10-02"},
            {"title": "Sin url", "content": "descartado"},
        ]})

    results = await _search(handler).search("precio Draxxin contacto ana@x.cl")

    assert seen["auth"] == "Bearer clave-tavily"
    assert "ana@x.cl" not in seen["body"]["query"] and seen["body"]["max_results"] == 3
    assert [r.url for r in results] == ["https://diario.cl/z"]
    assert len(results[0].snippet) == 400 and results[0].date == "2026-10-02"


@pytest.mark.anyio
async def test_a_query_with_only_personal_data_is_not_sent():
    def handler(request):
        raise AssertionError("no debia llamar al buscador")

    assert await _search(handler).search("juan@x.cl") == []


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 429, 500])
async def test_http_errors_become_a_search_error(status):
    with pytest.raises(WebSearchError):
        await _search(lambda request: httpx.Response(status)).search("zoetis")


@pytest.mark.anyio
async def test_network_failure_becomes_a_search_error():
    def handler(request):
        raise httpx.ConnectError("sin red")

    with pytest.raises(WebSearchError):
        await _search(handler).search("zoetis")
