"""
Lectura por la API REST de WordPress (`/wp-json/wp/v2`).

Se usa cuando la portada del medio mezcla noticias con programación, recetas o
avisos corporativos en rutas planas que ningún filtro de URL separa de forma
fiable. Es el caso de RTVC: raspar su portada metería ruido en el corpus y, con
las piezas sin tema ya almacenadas, ese ruido contaminaría el denominador.

La API devuelve solo entradas, y además dos cosas que el raspado de portada no
da: la fecha de publicación real y las categorías propias del medio.
"""

import html as _html
import json
import logging
import re
from typing import Optional

from observatorio.config.scraping import SCRAPER
from observatorio.recoleccion import fechas
from observatorio.recoleccion.clientes import ClienteHTTP

log = logging.getLogger("scraper")

_ETIQUETAS = re.compile(r"<[^>]+>")
_POR_PAGINA = 50

# Categorías administrativas que el medio pone en todas las entradas y que no
# describen la sección. Se descartan para que `seccion` diga algo.
_CATEGORIAS_RUIDO = {"rtvc-es", "sin-categoria", "uncategorized", "corporativa", "destacado"}


def _texto(fragmento: Optional[str]) -> str:
    """WordPress devuelve HTML incluso en el título y la entradilla."""
    if not fragmento:
        return ""
    return re.sub(r"\s+", " ", _html.unescape(_ETIQUETAS.sub(" ", fragmento))).strip()


def _cargar(cliente: ClienteHTTP, url: str) -> Optional[list]:
    crudo = cliente.get(url, usar_cache=False)
    if not crudo:
        return None
    try:
        datos = json.loads(crudo)
    except json.JSONDecodeError:
        log.warning("  wp-json: respuesta no es JSON en %s", url)
        return None
    return datos if isinstance(datos, list) else None


def _categorias(cliente: ClienteHTTP, api: str) -> dict[int, str]:
    """Mapa id → slug de categoría, para rellenar la columna `seccion`."""
    datos = _cargar(cliente, f"{api}/categories?per_page=100&_fields=id,slug")
    if not datos:
        return {}
    return {c["id"]: c["slug"] for c in datos if "id" in c and "slug" in c}


def parsear_wp_json(
    medio_id: str,
    cfg: dict,
    cliente: ClienteHTTP,
    max_items: int = 0,
) -> list[dict]:
    """Devuelve las entradas más recientes normalizadas al formato del scraper."""
    api = cfg.get("wp_api")
    if not api:
        log.warning("  %s declara tipo wp_json pero no define wp_api", medio_id)
        return []

    if max_items <= 0:
        max_items = SCRAPER["max_listado_por_medio"]
    por_pagina = min(_POR_PAGINA, max_items) if max_items else _POR_PAGINA

    log.info("  wp-json: %s", api)
    campos = "id,date,link,title,excerpt,categories"
    datos = _cargar(cliente, f"{api}/posts?per_page={por_pagina}&_fields={campos}")
    if not datos:
        log.warning("  wp-json inaccesible o vacío: %s", api)
        return []

    catalogo = _categorias(cliente, api)

    noticias = []
    for posicion, post in enumerate(datos, start=1):
        url = (post.get("link") or "").strip()
        titulo = _texto((post.get("title") or {}).get("rendered"))
        if not url or not titulo:
            continue

        secciones = [
            catalogo[c] for c in post.get("categories", [])
            if c in catalogo
            and catalogo[c] not in _CATEGORIAS_RUIDO
            and not catalogo[c].startswith("destacado")
        ]
        noticias.append({
            "medio": medio_id,
            "url": url,
            "titulo": titulo,
            # La API ya devuelve las entradas ordenadas de más a menos reciente.
            "posicion": posicion,
            "seccion": "/".join(secciones[:2]) or None,
            "resumen": _texto((post.get("excerpt") or {}).get("rendered"))[:800],
            # Fecha de publicación REAL, no la hora del raspado.
            "fecha_pub": fechas.parsear_fecha(post.get("date")) or fechas.ahora(),
            "fecha_pub_origen": (fechas.API if fechas.parsear_fecha(post.get("date"))
                                 else fechas.SINTETICA),
            "fuente": "wp_json",
            "raw": {
                "origen": "wp-json",
                "post_id": post.get("id"),
                "categorias": secciones,
            },
        })
        if max_items and len(noticias) >= max_items:
            break

    log.info("  → %d entradas wp-json en %s", len(noticias), api)
    return noticias
