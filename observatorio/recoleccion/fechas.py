"""
Fecha de publicación real, y de dónde salió.

El problema: las piezas que entran por portada reciben `datetime.now()` del
momento del raspado. Como el dashboard y cualquier análisis temporal leen
`fecha_pub`, para esas cabeceras la serie mide cuándo se ejecutó el scraper, no
cuándo publicó el medio.

Este módulo busca la fecha verdadera por cuatro vías, de más barata a más cara:

    url     · varios medios la llevan en la ruta (/2026/09/07/, /2026-09-04/,
              o un sello de 14 dígitos). No cuesta ninguna petición y sirve
              incluso para las piezas que no se descargan enteras. Precisión de
              día, sin hora.
    jsonld  · `datePublished` en los datos estructurados del artículo.
    meta    · <meta property="article:published_time"> y variantes.
    time    · <time datetime="…"> del cuerpo.

Y sobre todo registra la PROCEDENCIA junto a la fecha. Sin ella no se puede
distinguir una fecha real de la hora del raspado, y todo análisis temporal
queda a merced de una arqueología sobre `raw_json`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from bs4 import BeautifulSoup

# Procedencias posibles, de más a menos fiable
FEED = "feed"                    # pubDate del RSS
API = "api"                      # campo `date` de una API (wp-json)
JSONLD_ARTICULO = "jsonld"       # datePublished del artículo
META_ARTICULO = "meta"           # <meta article:published_time>
JSONLD_PORTADA = "jsonld_portada"
URL = "url"                      # extraída de la ruta; precisión de día
SINTETICA = "sintetica"          # hora del raspado: NO es fecha de publicación

_ANIO_MIN, _ANIO_MAX = 2000, datetime.now(timezone.utc).year + 1

_PATRONES_URL = (
    re.compile(r"/(?P<a>20\d{2})/(?P<m>\d{2})/(?P<d>\d{2})/"),        # /2026/09/07/
    re.compile(r"/(?P<a>20\d{2})-(?P<m>\d{2})-(?P<d>\d{2})/"),        # /2026-09-04/
    re.compile(r"-(?P<a>20\d{2})(?P<m>\d{2})(?P<d>\d{2})\d{6}\.html"),  # -20260907122506.html
)


def _plausible(a: int, m: int, d: int) -> bool:
    return _ANIO_MIN <= a <= _ANIO_MAX and 1 <= m <= 12 and 1 <= d <= 31


def parsear_fecha(valor: object) -> Optional[str]:
    """Normaliza a ISO 8601 con zona. Devuelve None si no hay fecha usable."""
    if not valor or not isinstance(valor, str):
        return None
    texto = valor.strip()
    if not texto:
        return None
    # `fromisoformat` de Python 3.11 acepta ya la Z y los desfases
    try:
        dt = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        # Último intento: solo la parte de fecha
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", texto)
        if not m:
            return None
        a, mes, d = (int(x) for x in m.groups())
        if not _plausible(a, mes, d):
            return None
        dt = datetime(a, mes, d, tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if not _ANIO_MIN <= dt.year <= _ANIO_MAX:
        return None
    return dt.isoformat()


def fecha_desde_url(url: str) -> Optional[str]:
    """
    Fecha embebida en la ruta. Gratis: no cuesta ninguna petición.

    Cubre a La Provincia, El Día, Canarias7, EFE y Europa Press. La precisión es
    de día —se devuelve a medianoche UTC—, así que sirve para agregar por día o
    semana, pero no para ordenar dentro de una jornada.
    """
    if not url:
        return None
    for patron in _PATRONES_URL:
        m = patron.search(url)
        if not m:
            continue
        a, mes, d = int(m.group("a")), int(m.group("m")), int(m.group("d"))
        if _plausible(a, mes, d):
            try:
                return datetime(a, mes, d, tzinfo=timezone.utc).isoformat()
            except ValueError:
                continue
    return None


def _fecha_desde_jsonld(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select("script[type='application/ld+json']"):
        crudo = script.get_text(strip=True)
        if not crudo:
            continue
        try:
            datos = json.loads(crudo)
        except json.JSONDecodeError:
            continue
        for blob in (datos if isinstance(datos, list) else [datos]):
            if not isinstance(blob, dict):
                continue
            for campo in ("datePublished", "dateCreated"):
                fecha = parsear_fecha(blob.get(campo))
                if fecha:
                    return fecha
    return None


def _fecha_desde_meta(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    selectores = (
        'meta[property="article:published_time"]',
        'meta[name="article:published_time"]',
        'meta[itemprop="datePublished"]',
        'meta[name="date"]',
        'meta[name="pubdate"]',
        'meta[property="og:published_time"]',
    )
    for sel in selectores:
        nodo = soup.select_one(sel)
        if nodo:
            fecha = parsear_fecha(nodo.get("content"))
            if fecha:
                return fecha
    nodo = soup.select_one("time[datetime]")
    if nodo:
        return parsear_fecha(nodo.get("datetime"))
    return None


def fecha_desde_html(html: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Busca la fecha en el HTML del artículo.

    Devuelve `(fecha_iso, procedencia)`, o `(None, None)` si no la encuentra.
    """
    if not html:
        return None, None
    fecha = _fecha_desde_jsonld(html)
    if fecha:
        return fecha, JSONLD_ARTICULO
    fecha = _fecha_desde_meta(html)
    if fecha:
        return fecha, META_ARTICULO
    return None, None


# Cuánto vale cada procedencia. Una fecha solo se sustituye por otra
# estrictamente mejor: la de URL tiene precisión de día y la mejora cualquiera
# con hora, pero la del feed no se pisa con la del artículo, que no aporta nada.
PRECEDENCIA = {
    SINTETICA: 0,
    URL: 1,
    JSONLD_PORTADA: 2,
    META_ARTICULO: 3,
    JSONLD_ARTICULO: 4,
    API: 5,
    FEED: 5,
}


def mejor_que(candidata: Optional[str], vigente: Optional[str]) -> bool:
    """¿Merece la pena sustituir la procedencia `vigente` por `candidata`?"""
    if candidata is None:
        return False
    return PRECEDENCIA.get(candidata, 0) > PRECEDENCIA.get(vigente or SINTETICA, 0)


def ahora() -> str:
    """Marca sintética: la hora del raspado. NO es fecha de publicación."""
    return datetime.now(timezone.utc).isoformat()
