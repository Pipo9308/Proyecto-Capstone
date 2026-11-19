import time
import hashlib
import logging
import httpx
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

DRAG_PHARMA_NOTICIAS_URL = "https://dragpharma.cl/noticias/"


def _get(url: str) -> BeautifulSoup:
    with httpx.Client(timeout=30, follow_redirects=True, headers=HEADERS) as client:
        r = client.get(url)
        r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def _extraer_resumen(url: str) -> str:
    try:
        soup    = _get(url)
        article = soup.select_one("article")
        if not article:
            return ""
        for tag in article.select("nav, header, footer, script, style, .share-buttons, .related-posts"):
            tag.decompose()
        texto = " ".join(article.get_text(separator=" ", strip=True).split())
        if len(texto) > 100:
            texto = texto[texto.find(" ", 50):]
        return texto[:400].strip()
    except Exception:
        return ""


def scrape_drag_pharma_noticias(max_paginas: int = 6) -> list[dict]:
    noticias = []
    vistas: set[str] = set()

    for pagina in range(1, max_paginas + 1):
        url_pagina = DRAG_PHARMA_NOTICIAS_URL if pagina == 1 else f"{DRAG_PHARMA_NOTICIAS_URL}page/{pagina}/"
        try:
            soup = _get(url_pagina)
        except httpx.HTTPStatusError:
            break

        articulos = soup.select("article")
        if not articulos:
            break

        for art in articulos:
            titulo_tag = art.select_one("h1,h2,h3,h4")
            fecha_tag  = art.select_one("time,.date,.posted-on")

            url = ""
            for a in art.find_all("a", href=True):
                href = a.get("href", "")
                if (
                    href.startswith("https://dragpharma.cl/")
                    and "mailto" not in href
                    and "/page/" not in href
                    and href.rstrip("/") != DRAG_PHARMA_NOTICIAS_URL.rstrip("/")
                ):
                    url = href
                    break

            if not titulo_tag or not url:
                continue

            doc_id = hashlib.md5(f"dragpharma_noticia_{url}".encode()).hexdigest()
            if doc_id in vistas:
                continue
            vistas.add(doc_id)

            titulo  = titulo_tag.get_text(strip=True)
            fecha   = fecha_tag.get_text(strip=True) if fecha_tag else ""
            resumen = _extraer_resumen(url)

            noticias.append({
                "id":      doc_id,
                "empresa": "DRAG PHARMA",
                "titulo":  titulo,
                "url":     url,
                "fecha":   fecha,
                "resumen": resumen,
            })

            time.sleep(0.5)

        time.sleep(1)

    return noticias


# Zoetis (sin seccion de noticias en zoetis.cl, news.zoetis.com bloquea con 403) y Agrovet (blog vacio):
# se leen noticias de prensa por RSS de Google News. (empresa, consulta, texto que debe llevar el titulo, texto que la descarta)
FUENTES_PRENSA = [
    ("ZOETIS",  '"Zoetis" Chile',                    "zoetis",  ""),
    # El competidor es AGROVET SPA (Chile). "Agrovet Market" es otra empresa (Peru): antes se buscaba esa por error.
    ("AGROVET", '"Agrovet" Chile -"Agrovet Market"', "agrovet", "agrovet market"),
]
# Google News limita las consultas seguidas (429): se reintenta esperando y se avisa si sigue bloqueado.
REINTENTOS_PRENSA = 2
ESPERA_MAX_S = 60
PAUSA_ENTRE_FUENTES_S = 5


def _espera(respuesta: httpx.Response, intento: int) -> float:
    """Segundos a esperar: lo que pide Google (Retry-After) o 20 s, 40 s..., con tope."""
    pedido = respuesta.headers.get("Retry-After", "")
    return min(float(pedido) if pedido.isdigit() else 20.0 * (intento + 1), ESPERA_MAX_S)


def scrape_prensa(empresa: str, consulta: str, clave: str, excluir: str = "", max_items: int = 30,
                  avisos: list[str] | None = None) -> list[dict]:
    """Noticias recientes (12 meses) de `empresa` desde Google News. Filtra los titulos que no nombran a la empresa
    o que nombran a la que se excluye. Si la fuente no responde, lo anota en `avisos` (la corrida queda parcial)."""
    log = logging.getLogger("agente_competidores")
    url = f"https://news.google.com/rss/search?q={quote(consulta + ' when:365d')}&hl=es-419&gl=CL&ceid=CL:es-419"
    r = None
    try:
        with httpx.Client(timeout=30, follow_redirects=True, headers=HEADERS) as client:
            for intento in range(REINTENTOS_PRENSA + 1):
                r = client.get(url)
                if (r.status_code == 429 or r.status_code >= 500) and intento < REINTENTOS_PRENSA:
                    espera = _espera(r, intento)
                    log.warning(f"Prensa {empresa}: HTTP {r.status_code}, se reintenta en {espera:.0f}s")
                    time.sleep(espera)
                    continue
                break
            r.raise_for_status()
    except httpx.HTTPError as e:
        motivo = "bloqueada por Google News (429)" if r is not None and r.status_code == 429 else type(e).__name__
        log.warning(f"Prensa {empresa}: {motivo}")
        if avisos is not None:
            avisos.append(f"Prensa {empresa}: {motivo}")
        return []

    noticias = []
    for item in ET.fromstring(r.content).iter("item"):
        if len(noticias) >= max_items:
            break
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        en_minusculas = titulo.lower()
        if not titulo or not link or clave not in en_minusculas or (excluir and excluir in en_minusculas):
            continue
        try:
            fecha = parsedate_to_datetime(item.findtext("pubDate")).date().isoformat()
        except (TypeError, ValueError):
            fecha = ""
        fuente = (item.findtext("source") or "").strip()
        noticias.append({
            "id":      hashlib.md5(f"prensa_{empresa}_{link}".encode()).hexdigest(),
            "empresa": empresa,
            "origen":  "prensa",
            "titulo":  titulo,
            "url":     link,
            "fecha":   fecha,
            "resumen": f"Fuente: {fuente}" if fuente else "",
        })
    return noticias


def scrape_todas(avisos: list[str] | None = None) -> list[dict]:
    """Todas las fuentes. Lo que no se pudo leer queda en `avisos` (si se pasa la lista)."""
    noticias = scrape_drag_pharma_noticias()
    for empresa, consulta, clave, excluir in FUENTES_PRENSA:
        time.sleep(PAUSA_ENTRE_FUENTES_S)  # consultas seguidas a Google News disparan el 429
        noticias += scrape_prensa(empresa, consulta, clave, excluir, avisos=avisos)
    return noticias


if __name__ == "__main__":
    print("=== DRAG PHARMA — NOTICIAS ===")
    noticias = scrape_todas()
    print(f"Total noticias: {len(noticias)}")
    for n in noticias:
        print(f"  [{n['fecha']}] {n['titulo']}")