"""
Lectura de feeds RSS/Atom.

Doble intento por diseño: primero `feedparser` fetcha la URL directamente (con
UA de navegador y Accept XML, más compatible con algunos WAF/CDN) y, si falla o
devuelve cero entradas, se reintenta con `httpx` a través de `ClienteHTTP`.

7 de las 17 cabeceras tienen un feed utilizable; el resto va por portada o por
la API de WordPress.
"""

import logging
import random
from datetime import datetime, timezone
from typing import Optional

import feedparser

from observatorio.comun.texto import limpiar_html, seccion_desde_url
from observatorio.config.scraping import SCRAPER, USER_AGENTS
from observatorio.recoleccion.clientes import ClienteHTTP, _esperar

log = logging.getLogger("scraper")

# ── Parsers ───────────────────────────────────────────────────────────────────

def _normalizar_fecha(entry) -> Optional[str]:
    """Extrae fecha ISO 8601 desde un entry de feedparser."""
    for campo in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, campo, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return None


def parsear_rss(
    medio_id: str,
    feed_url: str,
    cliente: ClienteHTTP,
    max_items: int = 0,
) -> list[dict]:
    """
    Parsea un feed RSS/Atom. Devuelve lista de noticias normalizadas.

    Estrategia de doble intento para maximizar disponibilidad:
      1. feedparser fetcha la URL directamente (UA de navegador, Accept XML,
         soporta ETag/Last-Modified — más compatible con algunos CDN/WAF).
      2. Si falla o devuelve 0 entradas, httpx como fallback con UA rotativo.
    """
    if max_items <= 0:
        max_items = SCRAPER["max_listado_por_medio"]

    log.info("  RSS: %s", feed_url)
    ua = random.choice(USER_AGENTS)

    # ── Intento 1: feedparser directo con cabeceras de navegador ─────────────
    # feedparser usa urllib internamente; al pasarle request_headers con un UA
    # real y Accept XML, evitamos que algunos WAF rechacen peticiones de bots.
    _esperar(feed=True)
    try:
        feed = feedparser.parse(
            feed_url,
            agent=ua,
            request_headers={
                "Accept": (
                    "application/rss+xml, application/atom+xml, "
                    "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7"
                ),
                "Accept-Language": "es-ES,es;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        log.warning("  feedparser directo falló en %s: %s", feed_url, e)
        feed = None

    # ── Intento 2: httpx con UA rotativo (fallback) ───────────────────────
    if not feed or (feed.bozo and not feed.entries):
        log.info("  RSS fallback httpx: %s", feed_url)
        html = cliente.get(feed_url, usar_cache=False, es_feed=True)
        if not html:
            log.warning("  Feed inaccesible (httpx): %s", feed_url)
            return []
        feed = feedparser.parse(html)

    if feed.bozo and not feed.entries:
        log.warning("  Feed malformado o vacío: %s", feed_url)
        return []

    noticias = []
    entradas = feed.entries[:max_items] if max_items > 0 else feed.entries
    for posicion, entry in enumerate(entradas, start=1):
        url = getattr(entry, "link", None)
        titulo = limpiar_html(getattr(entry, "title", ""))
        if not url or not titulo:
            continue

        resumen_raw = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or ""
        )
        etiquetas = [t.term for t in getattr(entry, "tags", [])]
        noticias.append({
            "medio": medio_id,
            "url": url.strip(),
            "titulo": titulo,
            # Rango dentro de ESTE feed. No es comparable con la posición en la
            # portada HTML: son dos listados distintos, y por eso viaja `fuente`.
            "posicion": posicion,
            "seccion": (etiquetas[0].lower() if etiquetas else seccion_desde_url(url)),
            "resumen": limpiar_html(resumen_raw)[:800],
            "fecha_pub": _normalizar_fecha(entry),
            "fuente": "rss",
            "raw": {
                "feed_url": feed_url,
                "feed_title": feed.feed.get("title", ""),
                "tags": etiquetas,
            },
        })

    log.info("  → %d entradas en %s", len(noticias), feed_url)
    return noticias
