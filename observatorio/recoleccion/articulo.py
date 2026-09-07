"""
Extracción del texto completo de un artículo.

Tres intentos en cascada: `articleBody` del JSON-LD, `newspaper3k`, y por
último una heurística de párrafos con BeautifulSoup. Se trunca a 5.000
caracteres.

Solo se llama DESPUÉS de que la noticia haya pasado el filtro temático, para no
gastar peticiones en artículos que se van a descartar.
"""

import json
import logging
from typing import Optional

from bs4 import BeautifulSoup

from observatorio.recoleccion.clientes import ClienteHTTP

log = logging.getLogger("scraper")

def _article_body_desde_jsonld(html: str) -> Optional[str]:
    """Intenta extraer articleBody desde bloques JSON-LD."""
    soup = BeautifulSoup(html, "html.parser")
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
            article_body = blob.get("articleBody")
            if article_body and len(str(article_body).strip()) > 100:
                return str(article_body).strip()[:5000]
    return None


def extraer_texto_articulo(url: str, cliente: ClienteHTTP) -> Optional[str]:
    """
    Descarga el artículo completo e intenta extraer el texto principal.
    Usa newspaper3k si está disponible, si no, heurística con BeautifulSoup.
    """
    html = cliente.get(url)
    if not html:
        return None

    # Muchos medios exponen el cuerpo completo en JSON-LD aunque newspaper falle.
    texto_jsonld = _article_body_desde_jsonld(html)
    if texto_jsonld:
        return texto_jsonld

    # Intentar con newspaper3k (mejor extracción)
    try:
        from newspaper import Article

        art = Article(url, language="es")
        art.set_html(html)
        art.parse()
        if art.text and len(art.text) > 100:
            return art.text[:5000]
    except ImportError:
        pass
    except Exception as e:
        log.debug("newspaper3k falló en %s: %s", url, e)

    # Fallback: heurística con BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for selector in [
        "article", "[class*='article-body']", "[class*='entry-content']",
        "[class*='news-body']", "main", ".content",
    ]:
        nodo = soup.select_one(selector)
        if nodo:
            parrafos = [
                p.get_text(strip=True)
                for p in nodo.find_all("p")
                if len(p.get_text()) > 40
            ]
            texto = " ".join(parrafos)
            if len(texto) > 100:
                return texto[:5000]

    return None
