"""
Orquestador del scraping.

`scrapear_medio()` ejecuta la cascada completa para una cabecera y deja traza en
la tabla `scraping_log`. `scrapear_todos()` la aplica a todos los medios,
aislando el fallo de cada uno para que no tumbe al resto.

El orden importa: se clasifica ANTES de descargar el artículo completo, de modo
que una noticia fuera de la agenda temática no cuesta ni una petición extra.
"""

import logging
import sqlite3
import time
from datetime import datetime, timezone
from typing import Optional

from observatorio.almacenamiento.sqlite import guardar_noticia, init_db, ya_existe
from observatorio.clasificacion.motor import clasificar
from observatorio.comun.registro import configurar_logging
from observatorio.config.medios import MEDIOS
from observatorio.config.scraping import SCRAPER
from observatorio.recoleccion.articulo import extraer_texto_articulo
from observatorio.recoleccion.clientes import (
    _PLAYWRIGHT_DISPONIBLE,
    ClienteHTTP,
    ClientePlaywright,
)
from observatorio.recoleccion.portada import parsear_html_portada
from observatorio.recoleccion.rss import parsear_rss

log = logging.getLogger("scraper")

# ── Orquestador principal ─────────────────────────────────────────────────────

def scrapear_medio(
    medio_id: str,
    conn: sqlite3.Connection,
    cliente: ClienteHTTP,
    dry_run: bool = False,
    extraer_articulos: bool = False,
) -> dict:
    """
    Scraping completo de un medio: RSS → HTML → (opcional) texto completo.
    Devuelve estadísticas del proceso.
    """
    cfg = MEDIOS.get(medio_id)
    if not cfg:
        raise ValueError(f"Medio '{medio_id}' no encontrado en config.py")

    log.info("━━ Scraping: %s ━━", cfg["nombre"])
    inicio = datetime.now(timezone.utc).isoformat()
    stats = {"medio": medio_id, "total": 0, "nuevas": 0, "errores": 0}
    status = "ok"

    # Registrar inicio en log de BD
    run_id = None
    if not dry_run:
        cur = conn.execute(
            "INSERT INTO scraping_log (medio, inicio) VALUES (?,?)",
            (medio_id, inicio),
        )
        conn.commit()
        run_id = cur.lastrowid

    # Cuota de este medio (puede sobreescribir el global de SCRAPER)
    max_items = cfg.get("max_items") or SCRAPER["max_items_por_medio"]

    # Cliente HTML: httpx por defecto; Playwright para medios JS-renderizados
    cliente_html: ClienteHTTP | ClientePlaywright = cliente
    cliente_pw: Optional[ClientePlaywright] = None
    if cfg.get("playwright"):
        if not _PLAYWRIGHT_DISPONIBLE:
            log.warning(
                "Playwright no disponible para %s — usando httpx como fallback. "
                "Instala con: pip install playwright && playwright install chromium",
                medio_id,
            )
        else:
            cliente_pw = ClientePlaywright()
            cliente_html = cliente_pw

    try:
        # Recolectar noticias
        noticias: list[dict] = []

        if cfg["tipo"] in ("rss_only", "rss+html"):
            for feed_url in cfg.get("rss", []):
                try:
                    noticias += parsear_rss(medio_id, feed_url, cliente, max_items=max_items)
                except Exception as e:
                    log.error("Error RSS %s: %s", feed_url, e)
                    stats["errores"] += 1

        if cfg["tipo"] in ("html_only", "rss+html"):
            try:
                noticias += parsear_html_portada(medio_id, cfg, cliente_html, max_items=max_items)
            except Exception as e:
                log.error("Error HTML %s: %s", cfg["url"], e)
                stats["errores"] += 1

        # Deduplicar por URL dentro de esta ejecución y aplicar cuota total del medio
        vistas = set()
        noticias_unicas = []
        for n in noticias:
            if n["url"] not in vistas:
                vistas.add(n["url"])
                noticias_unicas.append(n)
        noticias_unicas = noticias_unicas[:max_items]

        stats["total"] = len(noticias_unicas)
        log.info("  Total noticias únicas: %d", stats["total"])

        # Guardar / extraer texto completo
        for n in noticias_unicas:
            if dry_run:
                print(f"  [DRY-RUN] {n['medio']} | {n['titulo'][:70]}")
                stats["nuevas"] += 1
                continue

            if ya_existe(conn, n["url"]):
                continue

            temas = clasificar(
                n.get("titulo", ""),
                n.get("resumen", ""),
                n.get("url", ""),
            )
            if not temas:
                log.info("Noticia descartada sin temas: %s", n["titulo"][:80])
                continue

            n["temas"] = temas

            # Solo descargamos el artículo completo si ya pasó el filtro temático.
            if extraer_articulos:
                n["texto_full"] = extraer_texto_articulo(n["url"], cliente)

            if guardar_noticia(conn, n):
                stats["nuevas"] += 1
                log.info("  ✓ Nueva: %s", n["titulo"][:60])
    except Exception:
        status = "error"
        raise
    finally:
        if not dry_run and run_id:
            try:
                conn.execute(
                    """UPDATE scraping_log
                       SET fin=?, total=?, nuevas=?, errores=?, status=?
                       WHERE id=?""",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        stats["total"],
                        stats["nuevas"],
                        stats["errores"],
                        status,
                        run_id,
                    ),
                )
                conn.commit()
            except Exception:
                log.exception("No se pudo cerrar scraping_log para %s", medio_id)
        if cliente_pw:
            cliente_pw.close()

    log.info(
        "  Resultado: %d nuevas / %d total / %d errores",
        stats["nuevas"],
        stats["total"],
        stats["errores"],
    )
    return stats


def scrapear_todos(
    dry_run: bool = False,
    extraer_articulos: bool = False,
    medios: Optional[list[str]] = None,
) -> list[dict]:
    """Ejecuta el scraping para todos los medios (o los indicados)."""
    configurar_logging("scraper")
    conn = init_db()
    cliente = ClienteHTTP()
    medios_a_scrapear = medios or list(MEDIOS.keys())
    resultados = []
    inicio_total = time.time()

    log.info("Iniciando scraping de %d medios", len(medios_a_scrapear))
    try:
        for medio_id in medios_a_scrapear:
            if medio_id not in MEDIOS:
                log.warning("Medio desconocido: %s (ignorado)", medio_id)
                continue
            try:
                stats = scrapear_medio(
                    medio_id,
                    conn,
                    cliente,
                    dry_run=dry_run,
                    extraer_articulos=extraer_articulos,
                )
                resultados.append(stats)
            except Exception as e:
                log.error("Error fatal en medio %s: %s", medio_id, e, exc_info=True)
                resultados.append({"medio": medio_id, "error": str(e)})
    finally:
        cliente.close()
        conn.close()

    elapsed = time.time() - inicio_total
    total_nuevas = sum(r.get("nuevas", 0) for r in resultados)
    log.info("━━ Scraping completado en %.1fs — %d noticias nuevas ━━", elapsed, total_nuevas)

    return resultados
