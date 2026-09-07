"""
Extracción del contenido de un artículo: texto y fecha de publicación real.

Tres intentos en cascada: `articleBody` del JSON-LD, `newspaper3k`, y por
último una heurística de párrafos con BeautifulSoup. Se trunca a 5.000
caracteres.

Solo se llama DESPUÉS de que la noticia haya pasado el filtro temático, para no
gastar peticiones en artículos que se van a descartar. Por eso el texto y la
fecha se sacan de una única descarga: son los dos datos que solo están en la
página del artículo.
"""

import json
import logging
from typing import Optional

from bs4 import BeautifulSoup

from observatorio.recoleccion import fechas
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


def _texto_desde_html(url: str, html: str) -> Optional[str]:
    """Cuerpo del artículo: JSON-LD → newspaper3k → heurística de párrafos."""
    texto_jsonld = _article_body_desde_jsonld(html)
    if texto_jsonld:
        return texto_jsonld

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


def extraer_articulo(url: str, cliente: ClienteHTTP) -> dict:
    """
    Descarga el artículo una vez y devuelve lo que solo está en su página.

    `{"texto": str|None, "fecha_pub": str|None, "fecha_pub_origen": str|None}`

    La fecha es la razón de ser de esta función tanto como el texto: para las
    cabeceras que entran por portada, es la única forma de saber cuándo publicó
    el medio en lugar de cuándo pasó el scraper.
    """
    vacio = {"texto": None, "fecha_pub": None, "fecha_pub_origen": None}
    html = cliente.get(url)
    if not html:
        return vacio

    fecha, origen = fechas.fecha_desde_html(html)
    return {
        "texto": _texto_desde_html(url, html),
        "fecha_pub": fecha,
        "fecha_pub_origen": origen,
    }
