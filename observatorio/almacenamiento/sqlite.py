"""
Base de datos local (SQLite).

Aquí vive el esquema de `noticias` y `scraping_log`, incluida la migración
perezosa que añade columnas a bases antiguas.

`guardar_noticia()` es también el punto donde se aplica el filtro temático: si
la noticia no tiene ningún tema, no se guarda y devuelve False.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from observatorio.clasificacion.motor import clasificar
from observatorio.comun.texto import url_hash
from observatorio.config.rutas import DB_PATH

log = logging.getLogger("scraper")

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Crea la BD y las tablas si no existen. Devuelve conexión."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # escrituras concurrentes seguras
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS noticias (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT    NOT NULL UNIQUE,
            url_hash    TEXT    NOT NULL UNIQUE,
            medio       TEXT    NOT NULL,
            titulo      TEXT    NOT NULL,
            resumen     TEXT,
            texto_full  TEXT,
            fecha_pub   TEXT,
            fecha_scrap TEXT    NOT NULL,
            fuente      TEXT    NOT NULL,   -- 'rss' | 'html'
            raw_json    TEXT,               -- payload original del feed
            temas       TEXT,               -- JSON array de temas clasificados
            seccion     TEXT                -- sección propia del medio (feed o URL)
        );

        -- Una fila por pieza VISTA en cada ejecución, exista ya o no.
        --
        -- La tabla `noticias` guarda el alta: una fila por URL, la primera vez
        -- que aparece. Esta guarda la permanencia, que es la otra mitad de la
        -- saliencia: una pieza que aguanta cinco días en portada es más
        -- prominente que una que dura dos horas, y sin este registro esa
        -- diferencia se perdía en la ingesta y no era reconstruible después.
        CREATE TABLE IF NOT EXISTS observaciones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash     TEXT    NOT NULL,
            medio        TEXT    NOT NULL,
            run_id       TEXT    NOT NULL,   -- identificador de la ejecución
            observado_en TEXT    NOT NULL,   -- ISO 8601 UTC del momento de la observación
            posicion     INTEGER,            -- rango dentro de su listado de origen
            fuente       TEXT    NOT NULL,   -- 'rss' | 'html' | 'wp_json'
            UNIQUE (url_hash, run_id)
        );

        CREATE TABLE IF NOT EXISTS scraping_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            medio       TEXT    NOT NULL,
            inicio      TEXT    NOT NULL,
            fin         TEXT,
            total       INTEGER DEFAULT 0,
            nuevas      INTEGER DEFAULT 0,
            errores     INTEGER DEFAULT 0,
            status      TEXT    DEFAULT 'running'
        );

        CREATE INDEX IF NOT EXISTS idx_medio      ON noticias(medio);
        CREATE INDEX IF NOT EXISTS idx_fecha_pub  ON noticias(fecha_pub);
        CREATE INDEX IF NOT EXISTS idx_url_hash   ON noticias(url_hash);
        CREATE INDEX IF NOT EXISTS idx_obs_run    ON observaciones(run_id);
        CREATE INDEX IF NOT EXISTS idx_obs_hash   ON observaciones(url_hash);
        CREATE INDEX IF NOT EXISTS idx_obs_medio  ON observaciones(medio, observado_en);
    """)
    # Migración: añadir columnas nuevas si la BD ya existía sin ellas
    for col, defn in [("temas", "TEXT"), ("texto_full", "TEXT"), ("seccion", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE noticias ADD COLUMN {col} {defn}")
            conn.commit()
            log.info("Columna '%s' añadida a noticias (migración)", col)
        except sqlite3.OperationalError:
            pass  # ya existe

    log.info("BD inicializada en %s", db_path)
    return conn


def ya_existe(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM noticias WHERE url_hash = ?", (url_hash(url),)
    ).fetchone()
    return row is not None


def guardar_noticia(conn: sqlite3.Connection, noticia: dict) -> bool:
    """Inserta la pieza. Devuelve True si es nueva, False si ya estaba.

    Ya NO se descarta la pieza que no encaja en ningún tema: se guarda con
    `temas` vacío. Sin ella no hay denominador, y la saliencia es por definición
    una magnitud relativa al total de la producción del medio. Filtrar por tema
    es cosa de la consulta, no de la ingesta.
    """
    h = url_hash(noticia["url"])
    temas = noticia.get("temas")
    if temas is None:
        temas = clasificar(
            noticia.get("titulo", ""),
            noticia.get("resumen", ""),
            noticia.get("url", ""),
        )
    try:
        conn.execute(
            """INSERT INTO noticias
               (url, url_hash, medio, titulo, resumen, texto_full,
                fecha_pub, fecha_scrap, fuente, raw_json, temas, seccion)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                noticia["url"], h, noticia["medio"],
                noticia["titulo"], noticia.get("resumen"),
                noticia.get("texto_full"), noticia.get("fecha_pub"),
                datetime.now(timezone.utc).isoformat(),
                noticia["fuente"],
                json.dumps(noticia.get("raw"), ensure_ascii=False),
                json.dumps(temas, ensure_ascii=False),
                noticia.get("seccion"),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False   # duplicado, normal


def registrar_observacion(
    conn: sqlite3.Connection,
    noticia: dict,
    run_id: str,
    observado_en: str,
) -> bool:
    """
    Deja constancia de que la pieza estaba en portada en esta ejecución.

    Se llama SIEMPRE, aunque la pieza ya estuviera en la base: es lo que permite
    medir cuánto tiempo aguanta y en qué posición. Devuelve False si la pieza ya
    se había observado en esta misma ejecución (duplicado dentro de la tirada).
    """
    try:
        conn.execute(
            """INSERT INTO observaciones
               (url_hash, medio, run_id, observado_en, posicion, fuente)
               VALUES (?,?,?,?,?,?)""",
            (
                url_hash(noticia["url"]), noticia["medio"], run_id, observado_en,
                noticia.get("posicion"), noticia["fuente"],
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def conectar_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
