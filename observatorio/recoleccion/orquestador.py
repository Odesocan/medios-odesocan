"""
Orquestador del scraping.

`scrapear_medio()` ejecuta la cascada completa para una cabecera y deja traza en
la tabla `scraping_log`. `scrapear_todos()` la aplica a todos los medios,
aislando el fallo de cada uno para que no tumbe al resto.

Tres decisiones de diseño con consecuencias metodológicas:

1. Cada pieza vista deja una OBSERVACIÓN en cada ejecución, aunque ya estuviera
   en la base. La tabla `noticias` registra el alta; `observaciones` registra la
   permanencia, que es la otra mitad de la saliencia.

2. El listado de portada se recorre ENTERO. El tope está en la descarga de
   texto completo, que es lo que cuesta una petición por pieza.

3. Las piezas sin tema se guardan igual, con `temas` vacío, pero no se les
   descarga el cuerpo. Así hay denominador sin gastar tráfico.
"""

import logging
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from observatorio.almacenamiento.sqlite import (
    guardar_noticia,
    init_db,
    registrar_observacion,
    ya_existe,
)
from observatorio.clasificacion.motor import clasificar
from observatorio.comun.registro import configurar_logging
from observatorio.comun.texto import url_hash
from observatorio.config.medios import MEDIOS
from observatorio.config.scraping import SCRAPER
from observatorio.recoleccion import fechas
from observatorio.recoleccion.articulo import extraer_articulo
from observatorio.recoleccion.clientes import (
    _PLAYWRIGHT_DISPONIBLE,
    ClienteHTTP,
    ClientePlaywright,
)
from observatorio.recoleccion.portada import parsear_html_portada
from observatorio.recoleccion.rss import parsear_rss
from observatorio.recoleccion.wp_json import parsear_wp_json

log = logging.getLogger("scraper")


def nuevo_run_id() -> str:
    """Identificador de una tirada completa de scraping."""
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:6]}"


# ── Orquestador principal ─────────────────────────────────────────────────────

def scrapear_medio(
    medio_id: str,
    conn: sqlite3.Connection,
    cliente: ClienteHTTP,
    dry_run: bool = False,
    extraer_articulos: bool = False,
    run_id: Optional[str] = None,
    conocidas: Optional[set] = None,
) -> dict:
    """
    Scraping completo de un medio: RSS → HTML → (opcional) texto completo.
    Devuelve estadísticas del proceso.
    """
    cfg = MEDIOS.get(medio_id)
    if not cfg:
        raise ValueError(f"Medio '{medio_id}' no encontrado en config/medios.py")

    run_id = run_id or nuevo_run_id()
    log.info("━━ Scraping: %s ━━", cfg["nombre"])
    inicio = datetime.now(timezone.utc).isoformat()
    stats = {"medio": medio_id, "total": 0, "nuevas": 0, "observadas": 0,
             "sin_tema": 0, "con_texto": 0, "fecha_real": 0, "fecha_mejorada": 0,
             "errores": 0}
    status = "ok"

    # Registrar inicio en log de BD
    run_bd = None
    if not dry_run:
        cur = conn.execute(
            "INSERT INTO scraping_log (medio, inicio) VALUES (?,?)",
            (medio_id, inicio),
        )
        conn.commit()
        run_bd = cur.lastrowid

    # El listado se recorre entero (0 = sin tope); lo que se limita es la
    # descarga de artículos, que es lo que cuesta una petición por pieza.
    max_listado = SCRAPER["max_listado_por_medio"]
    presupuesto_texto = SCRAPER["max_articulos_por_medio"]

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
                    noticias += parsear_rss(medio_id, feed_url, cliente, max_items=max_listado)
                except Exception as e:
                    log.error("Error RSS %s: %s", feed_url, e)
                    stats["errores"] += 1

        if cfg["tipo"] in ("html_only", "rss+html"):
            try:
                noticias += parsear_html_portada(medio_id, cfg, cliente_html, max_items=max_listado)
            except Exception as e:
                log.error("Error HTML %s: %s", cfg["url"], e)
                stats["errores"] += 1

        if cfg["tipo"] == "wp_json":
            try:
                noticias += parsear_wp_json(medio_id, cfg, cliente, max_items=max_listado)
            except Exception as e:
                log.error("Error wp-json %s: %s", cfg.get("wp_api"), e)
                stats["errores"] += 1

        # Deduplicar por URL dentro de esta ejecución. Ya NO se recorta el
        # listado: la portada entera es la unidad de observación.
        vistas = set()
        noticias_unicas = []
        for n in noticias:
            if n["url"] not in vistas:
                vistas.add(n["url"])
                noticias_unicas.append(n)

        stats["total"] = len(noticias_unicas)
        log.info("  Total noticias únicas: %d", stats["total"])

        observado_en = datetime.now(timezone.utc).isoformat()
        conocidas_set = conocidas if conocidas is not None else set()

        for n in noticias_unicas:
            if dry_run:
                print(f"  [DRY-RUN] {n['medio']} | {n['titulo'][:70]}")
                stats["nuevas"] += 1
                continue

            # La observación se registra SIEMPRE, esté o no la pieza ya en la
            # base: es lo que mide cuánto aguanta en portada y en qué posición.
            if registrar_observacion(conn, n, run_id, observado_en):
                stats["observadas"] += 1

            # `conocidas` son los url_hash ya presentes en Supabase. Sin ellos,
            # en CI la base local está vacía y cada tirada del día volvería a
            # descargar el artículo de piezas que ya están en el corpus.
            if ya_existe(conn, n["url"]) or url_hash(n["url"]) in conocidas_set:
                continue

            temas = clasificar(
                n.get("titulo", ""),
                n.get("resumen", ""),
                n.get("url", ""),
            )
            n["temas"] = temas
            if not temas:
                stats["sin_tema"] += 1
            if n.get("fecha_pub_origen") != fechas.SINTETICA:
                stats["fecha_real"] += 1

            # El cuerpo solo se descarga para lo que entra en la agenda temática
            # y mientras quede presupuesto. Lo demás se guarda igual, para que
            # exista denominador, pero sin gastar una petición.
            if extraer_articulos and temas and presupuesto_texto > 0:
                articulo = extraer_articulo(n["url"], cliente)
                presupuesto_texto -= 1
                n["texto_full"] = articulo["texto"]
                if articulo["texto"]:
                    stats["con_texto"] += 1
                # La fecha del artículo solo sustituye a la que ya traía la
                # pieza si es estrictamente mejor: la del feed no se pisa, pero
                # la deducida de la URL (precisión de día) sí se mejora con una
                # que trae hora exacta.
                if fechas.mejor_que(articulo["fecha_pub_origen"], n.get("fecha_pub_origen")):
                    n["fecha_pub"] = articulo["fecha_pub"]
                    n["fecha_pub_origen"] = articulo["fecha_pub_origen"]
                    stats["fecha_mejorada"] += 1

            if guardar_noticia(conn, n):
                stats["nuevas"] += 1
                if temas:
                    log.info("  ✓ Nueva: %s", n["titulo"][:60])
    except Exception:
        status = "error"
        raise
    finally:
        if not dry_run and run_bd:
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
                        run_bd,
                    ),
                )
                conn.commit()
            except Exception:
                log.exception("No se pudo cerrar scraping_log para %s", medio_id)
        if cliente_pw:
            cliente_pw.close()

    log.info(
        "  Resultado: %d nuevas / %d observadas / %d en portada · %d sin tema · "
        "%d con texto · %d con fecha real (%d mejoradas) · %d errores",
        stats["nuevas"], stats["observadas"], stats["total"], stats["sin_tema"],
        stats["con_texto"], stats["fecha_real"], stats["fecha_mejorada"], stats["errores"],
    )
    return stats


def scrapear_todos(
    dry_run: bool = False,
    extraer_articulos: bool = False,
    medios: Optional[list[str]] = None,
    usar_conocidas: bool = True,
) -> list[dict]:
    """
    Ejecuta el scraping para todos los medios (o los indicados).

    `usar_conocidas` consulta a Supabase qué piezas ya están en el corpus para
    no volver a descargar sus artículos. Es lo que hace viable ejecutar varias
    veces al día sin multiplicar las peticiones a los medios.
    """
    configurar_logging("scraper")
    conn = init_db()
    cliente = ClienteHTTP()
    medios_a_scrapear = medios or list(MEDIOS.keys())
    run_id = nuevo_run_id()

    conocidas: set = set()
    if usar_conocidas and extraer_articulos:
        from observatorio.almacenamiento.postgres import hashes_conocidos
        conocidas = hashes_conocidos()
        log.info("Piezas ya en el corpus: %d (no se les volverá a pedir el artículo)",
                 len(conocidas))
    resultados = []
    inicio_total = time.time()

    log.info("Iniciando scraping de %d medios · run_id=%s", len(medios_a_scrapear), run_id)
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
                    run_id=run_id,
                    conocidas=conocidas,
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
    total_obs = sum(r.get("observadas", 0) for r in resultados)
    log.info("━━ Scraping completado en %.1fs — %d nuevas / %d observaciones ━━",
             elapsed, total_nuevas, total_obs)

    return resultados
