"""
supabase_loader.py — Sincroniza noticias desde SQLite local → Supabase (schema medios).

Uso:
    python supabase_loader.py              # Sincroniza todo lo pendiente
    python supabase_loader.py --limit 500  # Máximo de registros por ejecución
    python supabase_loader.py --dry-run    # Muestra qué se enviaría sin escribir
"""

import argparse
import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json

from clasificador import CLASIFICADOR_VERSION, clasificar
from config import DB_PATH, LOG_DIR, SUPABASE

log = logging.getLogger("supabase_loader")


def configurar_logging() -> None:
    """Configura logging por defecto si la aplicación aún no lo hizo."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / f"supabase_{datetime.now():%Y%m%d}.log"),
        ],
    )


# ── Conexiones ────────────────────────────────────────────────────────────────

def conectar_supabase() -> psycopg2.extensions.connection:
    missing = [
        key.upper()
        for key, value in SUPABASE.items()
        if key in {"host", "dbname", "user", "password", "schema"} and not value
    ]
    if missing:
        raise RuntimeError(
            "Faltan variables de entorno de Supabase: " + ", ".join(f"SUPABASE_{k}" for k in missing)
        )

    conn = psycopg2.connect(
        host=SUPABASE["host"],
        port=SUPABASE["port"],
        dbname=SUPABASE["dbname"],
        user=SUPABASE["user"],
        password=SUPABASE["password"],
        sslmode=SUPABASE["sslmode"],
    )
    conn.autocommit = False
    log.info("Conexión a Supabase establecida")
    return conn


def conectar_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Sincronización ────────────────────────────────────────────────────────────

def _hashes_en_supabase(pg: psycopg2.extensions.connection) -> set[str]:
    """Devuelve el conjunto de url_hash ya presentes en Supabase."""
    schema = SUPABASE["schema"]
    with pg.cursor() as cur:
        cur.execute(f"SELECT url_hash FROM {schema}.noticias")
        return {row[0] for row in cur.fetchall()}


def hashes_remotos() -> set[str]:
    """
    Igual que `_hashes_en_supabase`, pero abriendo y cerrando su propia
    conexión. Lo usa el scraper para saber qué piezas ya están en el corpus y
    no volver a descargarlas en cada una de las cuatro tiradas diarias.
    """
    pg = conectar_supabase()
    try:
        return _hashes_en_supabase(pg)
    finally:
        pg.close()


def _columnas(sq: sqlite3.Connection, tabla: str) -> set[str]:
    """Columnas realmente presentes en una tabla local."""
    return {fila["name"] for fila in sq.execute(f"PRAGMA table_info({tabla})").fetchall()}


# Columnas del régimen nuevo. Pueden faltar si la BD local se creó con una
# versión anterior del scraper: se rellenan a NULL en vez de reventar.
COLUMNAS_NOTICIA = [
    "url", "url_hash", "medio", "titulo", "resumen", "texto_full",
    "fecha_pub", "fecha_pub_origen", "fecha_scrap", "fuente", "raw_json",
    "temas", "clasificador_version", "seccion",
]


def _noticias_sqlite(
    sq: sqlite3.Connection,
    excluir_hashes: set[str],
    limit: Optional[int],
) -> list[dict]:
    """
    Lee de SQLite las noticias que aún no están en Supabase.

    El filtrado se hace en Python a propósito: pasar el conjunto de hashes
    remotos como parámetros de un NOT IN topa con el límite de variables de
    SQLite (32.766), y con cuatro tiradas diarias el corpus lo alcanza en
    semanas.
    """
    disponibles = _columnas(sq, "noticias")
    seleccion = [c for c in COLUMNAS_NOTICIA if c in disponibles]
    faltan = [c for c in COLUMNAS_NOTICIA if c not in disponibles]
    if faltan:
        log.warning("Columnas ausentes en la BD local (se envían vacías): %s", ", ".join(faltan))

    rows = sq.execute(
        f"SELECT {', '.join(seleccion)} FROM noticias ORDER BY fecha_scrap ASC"
    ).fetchall()

    pendientes = []
    for fila in rows:
        registro = dict(fila)
        if registro["url_hash"] in excluir_hashes:
            continue
        for columna in faltan:
            registro[columna] = None
        pendientes.append(registro)
        if limit and len(pendientes) >= limit:
            break
    return pendientes


def _normalizar_temas(temas_raw: object) -> list[str]:
    """Normaliza temas y descarta valores vacíos o equivalentes a NA."""
    if temas_raw is None:
        return []

    temas = temas_raw
    if isinstance(temas_raw, str):
        valor = temas_raw.strip()
        if not valor or valor.upper() == "NA" or valor.lower() == "null":
            return []
        try:
            temas = json.loads(valor)
        except json.JSONDecodeError:
            return []

    if isinstance(temas, str):
        temas = [temas]

    if not isinstance(temas, list):
        return []

    return [
        tema.strip()
        for tema in temas
        if isinstance(tema, str) and tema.strip() and tema.strip().upper() != "NA"
    ]


def _temas_para_supabase(noticia: dict) -> list[str]:
    """Devuelve los temas válidos guardados en SQLite."""
    return _normalizar_temas(noticia.get("temas"))


def sincronizar(
    dry_run: bool = False,
    limit: Optional[int] = None,
) -> dict:
    """
    Lee noticias de SQLite y las inserta en Supabase (upsert por url_hash).
    Devuelve estadísticas: total_locales, pendientes, insertadas, errores.
    """
    configurar_logging()
    sq = conectar_sqlite()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    stats = {
        "total_locales": 0,
        "sin_tema": 0,
        "pendientes": 0,
        "insertadas": 0,
        "errores": 0,
    }

    try:
        # Ya no se purga nada (R1): las piezas sin tema son el denominador y
        # viajan a Supabase con el array vacío. Quien no las quiera, que filtre
        # en la consulta; la vista pública `v_noticias_medios` ya lo hace.

        # Total en SQLite
        stats["total_locales"] = sq.execute("SELECT COUNT(*) FROM noticias").fetchone()[0]
        log.info("Total noticias en SQLite: %d", stats["total_locales"])

        # Qué ya está en Supabase
        ya_subidas = _hashes_en_supabase(pg)
        log.info("Ya en Supabase: %d", len(ya_subidas))

        # Pendientes
        pendientes = _noticias_sqlite(sq, ya_subidas, limit)
        stats["pendientes"] = len(pendientes)
        log.info("Pendientes de sincronizar: %d", stats["pendientes"])

        if dry_run:
            for n in pendientes:
                print(f"  [DRY-RUN] {n['medio']} | {n['titulo'][:70]}")
            return stats

        if not pendientes:
            log.info("Nada que sincronizar.")
            return stats

        stats["sin_tema"] = sum(1 for n in pendientes if not _temas_para_supabase(n))
        log.info(
            "  de las cuales sin tema (denominador): %d (%.1f %%)",
            stats["sin_tema"],
            100.0 * stats["sin_tema"] / max(len(pendientes), 1),
        )

        # Insertar en lotes de 200
        lote_size = 200
        insert_sql = f"""
            INSERT INTO {schema}.noticias
                (url, url_hash, medio, titulo, resumen, texto_full,
                 fecha_pub, fecha_pub_origen, fecha_scrap, fuente, raw_json,
                 temas, clasificador_version, seccion)
            VALUES %s
            ON CONFLICT (url_hash) DO NOTHING
        """

        for i in range(0, len(pendientes), lote_size):
            lote = pendientes[i : i + lote_size]
            valores = [
                (
                    n["url"],
                    n["url_hash"],
                    n["medio"],
                    n["titulo"],
                    n.get("resumen"),
                    n.get("texto_full"),
                    n.get("fecha_pub"),
                    n.get("fecha_pub_origen"),
                    n.get("fecha_scrap"),
                    n["fuente"],
                    Json(json.loads(n["raw_json"])) if n.get("raw_json") else None,
                    _temas_para_supabase(n),
                    n.get("clasificador_version"),
                    n.get("seccion"),
                )
                for n in lote
            ]
            try:
                with pg.cursor() as cur:
                    psycopg2.extras.execute_values(cur, insert_sql, valores)
                pg.commit()
                stats["insertadas"] += len(lote)
                log.info(
                    "  ✓ Lote %d-%d insertado (%d registros)",
                    i + 1,
                    i + len(lote),
                    len(lote),
                )
            except Exception as e:
                pg.rollback()
                stats["errores"] += len(lote)
                log.error("Error en lote %d-%d: %s", i + 1, i + len(lote), e, exc_info=True)

        log.info(
            "Sincronización completada — %d insertadas / %d errores",
            stats["insertadas"],
            stats["errores"],
        )

    finally:
        sq.close()
        pg.close()

    return stats


def actualizar_temas_vacios() -> int:
    """
    Etiqueta en Supabase los registros con `temas` a NULL.

    NULL y array vacío no son lo mismo: NULL significa «no se ha pasado el
    clasificador por aquí», y vacío significa «clasificado, y no cae en ninguno
    de los 15 temas». Lo segundo es un dato, no un descarte, así que ya no se
    borra nada (R1): se escribe el array vacío y se sella con la versión del
    clasificador que tomó la decisión (R3).
    """
    configurar_logging()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    con_tema = 0
    sin_tema = 0
    try:
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                f"SELECT url_hash, titulo, resumen, url FROM {schema}.noticias WHERE temas IS NULL"
            )
            filas = cur.fetchall()

        if not filas:
            log.info("No hay registros sin clasificar en Supabase.")
            return 0

        log.info("Clasificando %d registros con temas a NULL…", len(filas))
        with pg.cursor() as cur:
            for fila in filas:
                temas = clasificar(
                    fila["titulo"] or "",
                    fila["resumen"] or "",
                    fila["url"] or "",
                )
                cur.execute(
                    f"""UPDATE {schema}.noticias
                        SET temas = %s, clasificador_version = %s
                        WHERE url_hash = %s""",
                    (temas, CLASIFICADOR_VERSION, fila["url_hash"]),
                )
                if temas:
                    con_tema += 1
                else:
                    sin_tema += 1
        pg.commit()
        log.info(
            "Clasificación completada: %d con tema, %d sin tema (denominador)",
            con_tema, sin_tema,
        )
    except Exception as e:
        pg.rollback()
        log.error("Error actualizando temas: %s", e, exc_info=True)
    finally:
        pg.close()
    return con_tema + sin_tema


def sincronizar_observaciones(limit: Optional[int] = None) -> dict:
    """
    Copia a Supabase la tabla local de observaciones (R2).

    Una fila por pieza y tirada. Es lo que sostiene la duración de la atención
    y la prominencia, y lo único del pipeline que crece con el tiempo aunque no
    entren piezas nuevas: una pieza que aguanta una semana en portada deja
    veintiocho observaciones.
    """
    configurar_logging()
    sq = conectar_sqlite()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    stats = {"locales": 0, "pendientes": 0, "insertadas": 0, "errores": 0}

    try:
        if "observaciones" not in {
            fila["name"]
            for fila in sq.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }:
            log.info("No hay tabla local de observaciones todavía.")
            return stats

        filas = sq.execute(
            "SELECT url_hash, medio, run_id, observado_en, posicion, fuente "
            "FROM observaciones ORDER BY observado_en ASC"
        ).fetchall()
        stats["locales"] = len(filas)
        if not filas:
            log.info("Sin observaciones que sincronizar.")
            return stats

        # Solo se consultan las tiradas presentes en local: la tabla remota
        # crece sin techo y traérsela entera sería absurdo.
        run_ids = sorted({fila["run_id"] for fila in filas})
        with pg.cursor() as cur:
            cur.execute(
                f"SELECT url_hash, run_id FROM {schema}.observaciones WHERE run_id = ANY(%s)",
                (run_ids,),
            )
            ya_en_pg = {(row[0], row[1]) for row in cur.fetchall()}

        pendientes = [
            fila for fila in filas
            if (fila["url_hash"], fila["run_id"]) not in ya_en_pg
        ]
        if limit:
            pendientes = pendientes[:limit]
        stats["pendientes"] = len(pendientes)
        if not pendientes:
            log.info("Observaciones ya sincronizadas.")
            return stats

        lote_size = 500
        insert_sql = f"""
            INSERT INTO {schema}.observaciones
                (url_hash, medio, run_id, observado_en, posicion, fuente)
            VALUES %s
            ON CONFLICT DO NOTHING
        """
        for i in range(0, len(pendientes), lote_size):
            lote = pendientes[i : i + lote_size]
            valores = [
                (
                    fila["url_hash"], fila["medio"], fila["run_id"],
                    fila["observado_en"], fila["posicion"], fila["fuente"],
                )
                for fila in lote
            ]
            try:
                with pg.cursor() as cur:
                    psycopg2.extras.execute_values(cur, insert_sql, valores)
                pg.commit()
                stats["insertadas"] += len(lote)
            except Exception as e:
                pg.rollback()
                stats["errores"] += len(lote)
                log.error("Error en lote de observaciones %d: %s", i, e, exc_info=True)

        log.info(
            "Observaciones sincronizadas: %d de %d locales (%d errores)",
            stats["insertadas"], stats["locales"], stats["errores"],
        )
    finally:
        sq.close()
        pg.close()

    return stats


def sincronizar_log(run_stats: list[dict]) -> None:
    """
    Copia el scraping_log de SQLite a Supabase.
    Solo inserta las entradas con status='ok' aún no presentes.
    """
    configurar_logging()
    sq = conectar_sqlite()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]

    try:
        # Fechas de inicio ya en Supabase
        with pg.cursor() as cur:
            cur.execute(f"SELECT inicio::text FROM {schema}.scraping_log")
            ya_en_pg = {row[0][:19] for row in cur.fetchall()}  # truncar a segundos

        filas = sq.execute(
            "SELECT medio, inicio, fin, total, nuevas, errores, status "
            "FROM scraping_log WHERE status = 'ok'"
        ).fetchall()

        pendientes = [
            dict(r) for r in filas
            if (r["inicio"] or "")[:19] not in ya_en_pg
        ]

        if not pendientes:
            return

        valores = [
            (r["medio"], r["inicio"], r["fin"], r["total"], r["nuevas"], r["errores"], r["status"])
            for r in pendientes
        ]
        with pg.cursor() as cur:
            psycopg2.extras.execute_values(
                cur,
                f"""INSERT INTO {schema}.scraping_log
                    (medio, inicio, fin, total, nuevas, errores, status)
                    VALUES %s ON CONFLICT DO NOTHING""",
                valores,
            )
        pg.commit()
        log.info("scraping_log: %d entradas sincronizadas", len(pendientes))

    except Exception as e:
        pg.rollback()
        log.error("Error sincronizando scraping_log: %s", e, exc_info=True)
    finally:
        sq.close()
        pg.close()


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    configurar_logging()
    parser = argparse.ArgumentParser(description="Sincroniza SQLite → Supabase (schema medios)")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Máximo de noticias a enviar por ejecución",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra pendientes sin escribir en Supabase",
    )
    args = parser.parse_args()

    stats = sincronizar(dry_run=args.dry_run, limit=args.limit)
    if not args.dry_run:
        sincronizar_log([])
        stats_obs = sincronizar_observaciones()
        stats.update({f"obs_{k}": v for k, v in stats_obs.items()})
        actualizar_temas_vacios()

    print("\nResumen:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
