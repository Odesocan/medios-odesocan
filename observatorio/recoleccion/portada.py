"""
Extracción de titulares desde la portada HTML.

Dos vías, en este orden:

1. Selectores CSS definidos por medio en `config/medios.py`.
2. JSON-LD (`ItemList`, `NewsArticle`) como red de seguridad: si los selectores
   devuelven menos de la mitad de la cuota, se buscan los datos estructurados.
   Esto es lo que salva al scraper cuando un medio cambia de plantilla.

`_url_html_permitida()` aplica los filtros `html_url_regex` y
`html_url_excludes` del medio para descartar navegación, taxonomías y tickers.
"""

import json
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from observatorio.comun.texto import seccion_desde_url
from observatorio.config.scraping import SCRAPER
from observatorio.recoleccion.clientes import ClientePlaywright

log = logging.getLogger("scraper")

def _extraer_desde_jsonld_portada(html: str, medio_id: str, cfg: dict, max_items: int) -> list[dict]:
    """
    Extrae noticias desde bloques JSON-LD (ItemList, NewsArticle) en la portada.
    Muchos CMS modernos incluyen datos estructurados incluso cuando los selectores
    CSS cambian — esto actúa como red de seguridad complementaria.
    """
    soup = BeautifulSoup(html, "html.parser")
    noticias: list[dict] = []
    vistos: set[str] = set()

    for script in soup.select("script[type='application/ld+json']"):
        raw = script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if not isinstance(blob, dict):
                continue

            # ItemList con ListItem elements
            if blob.get("@type") == "ItemList":
                for item in blob.get("itemListElement", []):
                    url = item.get("url", "").strip()
                    nombre = item.get("name", "").strip()
                    if url and nombre and url not in vistos:
                        if _url_html_permitida(url, cfg):
                            vistos.add(url)
                            noticias.append({
                                "medio": medio_id,
                                "url": url,
                                "titulo": nombre,
                                "posicion": len(noticias) + 1,
                                "seccion": seccion_desde_url(url),
                                "resumen": "",
                                "fecha_pub": datetime.now(timezone.utc).isoformat(),
                                "fuente": "html",
                                "raw": {"origen": "json-ld", "tipo": "ItemList"},
                            })

            # NewsArticle / Article individual
            elif blob.get("@type") in ("NewsArticle", "Article", "ReportageNewsArticle"):
                url = blob.get("url", blob.get("mainEntityOfPage", ""))
                if isinstance(url, dict):
                    url = url.get("@id", "")
                titulo = blob.get("headline", "").strip()
                if url and titulo and url not in vistos:
                    if _url_html_permitida(url, cfg):
                        vistos.add(url)
                        noticias.append({
                            "medio": medio_id,
                            "url": url,
                            "titulo": titulo,
                            "posicion": len(noticias) + 1,
                            "seccion": seccion_desde_url(url),
                            "resumen": (blob.get("description") or "")[:800],
                            "fecha_pub": blob.get("datePublished") or datetime.now(timezone.utc).isoformat(),
                            "fuente": "html",
                            "raw": {"origen": "json-ld", "tipo": blob.get("@type")},
                        })

            if max_items and len(noticias) >= max_items:
                break

    return noticias[:max_items] if max_items else noticias


def parsear_html_portada(
    medio_id: str,
    cfg: dict,
    cliente,          # ClienteHTTP o ClientePlaywright (duck-typing: ambos tienen .get(url))
    max_items: int = 0,
) -> list[dict]:
    """
    Extrae titulares de la portada HTML como fallback o complemento al RSS.
    Usa los selectores CSS definidos en config.py.
    Acepta tanto ClienteHTTP (httpx) como ClientePlaywright (Chromium headless).

    Estrategia de doble extracción:
      1. Selectores CSS (fuente principal, configurable por medio)
      2. JSON-LD / datos estructurados (red de seguridad ante cambios de template)
    """
    if not cfg.get("selectores"):
        return []
    if max_items <= 0:
        max_items = SCRAPER["max_listado_por_medio"]

    motor = "Playwright" if isinstance(cliente, ClientePlaywright) else "HTML"
    log.info("  %s: %s", motor, cfg["url"])
    # Sin caché: el listado de portada cambia a diario y la caché dura 7 días.
    # Servirlo caducado fabricaría permanencia falsa en la tabla de observaciones.
    # (La caché sigue teniendo sentido para el cuerpo de los artículos, que no
    # cambia; eso lo hace recoleccion/articulo.py.)
    html = cliente.get(cfg["url"], usar_cache=False)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    sel_titular = cfg["selectores"].get("titular", "h2 a")
    sel_resumen = cfg["selectores"].get("resumen", "")

    vistos: set[str] = set()
    noticias: list[dict] = []

    for enlace in soup.select(sel_titular):
        titulo = enlace.get_text(strip=True)
        href = enlace.get("href", "").strip()
        if not titulo or not href:
            continue
        if href.startswith(("#", "javascript:", "mailto:")):
            continue

        url = urljoin(cfg["url"], href)
        if not _url_html_permitida(url, cfg):
            continue
        if url in vistos:
            continue
        vistos.add(url)

        # Intentar obtener resumen del nodo adyacente
        resumen = ""
        if sel_resumen:
            parent = enlace.find_parent(["article", "div", "li", "section"])
            if parent:
                nodo_res = parent.select_one(sel_resumen)
                if nodo_res:
                    resumen = nodo_res.get_text(strip=True)[:800]

        noticias.append({
            "medio": medio_id,
            "url": url,
            "titulo": titulo,
            # Rango en el orden del DOM de la portada, que aproxima la prominencia
            # visual. Es una aproximación: el CSS puede reordenar lo que se ve.
            "posicion": len(noticias) + 1,
            "seccion": seccion_desde_url(url),
            "resumen": resumen,
            "fecha_pub": datetime.now(timezone.utc).isoformat(),
            "fuente": "html",
            "raw": {"origen": "portada", "selector": sel_titular},
        })
        if max_items and len(noticias) >= max_items:
            break

    # ── Fallback JSON-LD: complementar si los selectores CSS dieron pocos resultados
    if len(noticias) < (max_items // 2 if max_items else 8):
        log.info("  JSON-LD fallback (selectores CSS dieron solo %d)", len(noticias))
        jsonld_noticias = _extraer_desde_jsonld_portada(html, medio_id, cfg, max_items)
        for n in jsonld_noticias:
            if n["url"] not in vistos:
                vistos.add(n["url"])
                noticias.append(n)
                if max_items and len(noticias) >= max_items:
                    break

    log.info("  → %d titulares %s en %s", len(noticias), motor, cfg["url"])
    return noticias


def _url_html_permitida(url: str, cfg: dict) -> bool:
    """Aplica filtros opcionales para aceptar solo URLs de artículo útiles."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    url_norm = url.lower()
    for patron in cfg.get("html_url_excludes", []):
        if patron.lower() in url_norm:
            return False

    regex = cfg.get("html_url_regex")
    if regex and not re.search(regex, url):
        return False

    return True
