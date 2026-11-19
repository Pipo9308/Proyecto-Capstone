"""Prensa del agente Competidores: reintento ante el bloqueo de Google News, aviso de corrida parcial y Agrovet correcto."""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "agents" / "agent-competidores"))
import scraper  # noqa: E402

RSS = """<rss><channel>
<item><title>Agrovet SpA abre nueva planta en Santiago - Diario</title><link>https://n/1</link>
  <pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate><source>Diario</source></item>
<item><title>Agrovet Market exporta a 40 paises - Gestion</title><link>https://n/2</link>
  <pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate><source>Gestion</source></item>
<item><title>Otra empresa sin relacion</title><link>https://n/3</link>
  <pubDate>Mon, 16 Nov 2026 10:00:00 GMT</pubDate></item>
</channel></rss>"""


def _google(monkeypatch, estados):
    """Cliente falso: responde los codigos de `estados` en orden; un 200 trae el RSS."""
    pedidos, esperas = [], []

    class Cliente:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):
            pedidos.append(url)
            codigo = estados.pop(0)
            return httpx.Response(codigo, content=RSS.encode() if codigo == 200 else b"", headers={"Retry-After": "7"},
                                  request=httpx.Request("GET", url))

    monkeypatch.setattr(scraper.httpx, "Client", Cliente)
    monkeypatch.setattr(scraper.time, "sleep", esperas.append)
    return pedidos, esperas


def test_agrovet_busca_la_empresa_chilena_y_descarta_agrovet_market(monkeypatch):
    pedidos, _ = _google(monkeypatch, [200])
    empresa, consulta, clave, excluir = next(f for f in scraper.FUENTES_PRENSA if f[0] == "AGROVET")

    noticias = scraper.scrape_prensa(empresa, consulta, clave, excluir)

    assert [n["titulo"] for n in noticias] == ["Agrovet SpA abre nueva planta en Santiago - Diario"]
    assert "Chile" in consulta and "-%22Agrovet%20Market%22" in pedidos[0]


def test_un_bloqueo_pasajero_se_reintenta_esperando_lo_que_pide_google(monkeypatch):
    pedidos, esperas = _google(monkeypatch, [429, 200])
    avisos = []

    noticias = scraper.scrape_prensa("AGROVET", "x", "agrovet", "agrovet market", avisos=avisos)

    assert len(pedidos) == 2 and esperas == [7.0] and len(noticias) == 1 and avisos == []


def test_si_google_sigue_bloqueando_la_corrida_queda_con_aviso(monkeypatch):
    pedidos, esperas = _google(monkeypatch, [429, 429, 429])
    avisos = []

    assert scraper.scrape_prensa("ZOETIS", "x", "zoetis", avisos=avisos) == []
    assert len(pedidos) == 1 + scraper.REINTENTOS_PRENSA
    assert avisos == ["Prensa ZOETIS: bloqueada por Google News (429)"]


def test_scrape_todas_junta_los_avisos_de_cada_fuente(monkeypatch):
    _google(monkeypatch, [429] * 10)
    monkeypatch.setattr(scraper, "scrape_drag_pharma_noticias", lambda: [{"id": "d1", "titulo": "Drag"}])
    avisos = []

    noticias = scraper.scrape_todas(avisos)

    assert noticias == [{"id": "d1", "titulo": "Drag"}]
    assert avisos == ["Prensa ZOETIS: bloqueada por Google News (429)", "Prensa AGROVET: bloqueada por Google News (429)"]
