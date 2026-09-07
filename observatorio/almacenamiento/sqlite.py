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
            temas       TEXT                -- JSON array de temas clasificados
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
    """)
    # Migración: añadir columnas nuevas si la BD ya existía sin ellas
    for col, defn in [("temas", "TEXT"), ("texto_full", "TEXT")]:
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
    """Inserta noticia. Devuelve True si es nueva, False si ya existía."""
    h = url_hash(noticia["url"])
    temas = noticia.get("temas") or clasificar(
        noticia.get("titulo", ""),
        noticia.get("resumen", ""),
        noticia.get("url", ""),
    )
    if not temas:
        log.info("Noticia descartada sin temas: %s", noticia["titulo"][:80])
        return False
    try:
        conn.execute(
            """INSERT INTO noticias
               (url, url_hash, medio, titulo, resumen, texto_full,
                fecha_pub, fecha_scrap, fuente, raw_json, temas)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                noticia["url"], h, noticia["medio"],
                noticia["titulo"], noticia.get("resumen"),
                noticia.get("texto_full"), noticia.get("fecha_pub"),
                datetime.now(timezone.utc).isoformat(),
                noticia["fuente"],
                json.dumps(noticia.get("raw"), ensure_ascii=False),
                json.dumps(temas, ensure_ascii=False),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False   # duplicado, normal


def conectar_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
