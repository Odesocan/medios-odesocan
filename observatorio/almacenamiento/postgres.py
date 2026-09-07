"""
Sincronización SQLite → PostgreSQL (Supabase).

Conexión Postgres directa con psycopg2 contra el pooler, NO el cliente REST de
Supabase (ese solo lo usa el pipeline de la nube de palabras).

Tres operaciones:

    sincronizar()             vuelca lo nuevo, en lotes de 200, upsert por url_hash
    sincronizar_log()         copia la traza de ejecuciones
    actualizar_temas_vacios() reclasifica en Postgres lo que quedó sin tema

La tercera NO forma parte del pipeline automático: solo se lanza desde
`bin/sincronizar.py`.
"""

import json
import logging
import sqlite3
from typing import Optional

import psycopg2
import psycopg2.extras
from psycopg2.extras import Json

from observatorio.almacenamiento.sqlite import conectar_sqlite
from observatorio.clasificacion.motor import clasificar
from observatorio.clasificacion.version import version_clasificador
from observatorio.comun.registro import configurar_logging
from observatorio.config.credenciales import SUPABASE

log = logging.getLogger("postgres")

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


# ── Sincronización ────────────────────────────────────────────────────────────

def hashes_conocidos() -> set[str]:
    """
    `url_hash` que ya están en Supabase, para no repetir trabajo entre tiradas.

    Hace falta porque en GitHub Actions la SQLite arranca vacía en cada
    ejecución: `ya_existe()` mira la base local y siempre dice que no, de modo
    que con varias tiradas al día se volvería a descargar el artículo completo
    de piezas que ya están en el corpus. Con una sola tirada diaria daba igual;
    con cuatro, multiplica por cuatro las peticiones a los medios.

    Si Supabase no está disponible devuelve un conjunto vacío, que es el
    comportamiento de siempre: se pierde eficiencia, no corrección.
    """
    try:
        pg = conectar_supabase()
    except Exception as e:
        log.warning("No se pudieron leer los hashes conocidos (%s); se sigue sin ellos", e)
        return set()
    try:
        return _hashes_en_supabase(pg)
    except Exception as e:
        log.warning("Error leyendo los hashes conocidos: %s", e)
        return set()
    finally:
        pg.close()


def _hashes_en_supabase(pg: psycopg2.extensions.connection) -> set[str]:
    """Devuelve el conjunto de url_hash ya presentes en Supabase."""
    schema = SUPABASE["schema"]
    with pg.cursor() as cur:
        cur.execute(f"SELECT url_hash FROM {schema}.noticias")
        return {row[0] for row in cur.fetchall()}


def _noticias_sqlite(
    sq: sqlite3.Connection,
    excluir_hashes: set[str],
    limit: Optional[int],
) -> list[dict]:
    """Lee de SQLite las noticias que aún no están en Supabase."""
    placeholders = ",".join("?" * len(excluir_hashes)) if excluir_hashes else "''"
    query = f"""
        SELECT url, url_hash, medio, titulo, resumen, texto_full,
               fecha_pub, fecha_scrap, fuente, raw_json, temas, seccion,
               clasificador_version, fecha_pub_origen
        FROM noticias
        {"WHERE url_hash NOT IN (" + placeholders + ")" if excluir_hashes else ""}
        ORDER BY fecha_scrap ASC
        {"LIMIT " + str(limit) if limit else ""}
    """
    params = tuple(excluir_hashes) if excluir_hashes else ()
    rows = sq.execute(query, params).fetchall()
    return [dict(r) for r in rows]


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


def _sin_tema(sq: sqlite3.Connection) -> int:
    """Cuenta las piezas sin tema. Antes esta función las BORRABA.

    Se conservan a propósito: son el denominador. Sin ellas solo puede
    calcularse la cuota dentro de la agenda de ODESOCAN, no dentro de la
    producción del medio, que es lo que mide la saliencia.
    """
    filas = sq.execute("SELECT temas FROM noticias").fetchall()
    return sum(1 for f in filas if not _normalizar_temas(f["temas"]))


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
    configurar_logging("supabase")
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
        stats["sin_tema"] = _sin_tema(sq)

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

        # Insertar en lotes de 200
        lote_size = 200
        insert_sql = f"""
            INSERT INTO {schema}.noticias
                (url, url_hash, medio, titulo, resumen, texto_full,
                 fecha_pub, fecha_scrap, fuente, raw_json, temas, seccion,
                 clasificador_version, fecha_pub_origen)
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
                    n.get("fecha_scrap"),
                    n["fuente"],
                    Json(json.loads(n["raw_json"])) if n.get("raw_json") else None,
                    _temas_para_supabase(n),
                    n.get("seccion"),
                    n.get("clasificador_version"),
                    n.get("fecha_pub_origen"),
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
    """Reclasifica en Supabase los registros con `temas` a NULL.

    Los que sigan sin encajar en ningún tema quedan con array vacío, no se
    borran: son parte del denominador.
    """
    configurar_logging("supabase")
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    actualizados = 0
    sin_tema = 0
    try:
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(f"SELECT url_hash, titulo, resumen FROM {schema}.noticias WHERE temas IS NULL")
            filas = cur.fetchall()

        if not filas:
            log.info("No hay registros sin temas en Supabase.")
            return 0

        log.info("Reclasificando %d registros sin temas…", len(filas))
        with pg.cursor() as cur:
            for fila in filas:
                temas = clasificar(fila["titulo"] or "", fila["resumen"] or "")
                # Antes, las que seguían sin tema se BORRABAN. Ahora se marcan
                # con array vacío: siguen contando para el denominador.
                cur.execute(
                    f"""UPDATE {schema}.noticias
                        SET temas = %s, clasificador_version = %s
                        WHERE url_hash = %s""",
                    (temas, version_clasificador(), fila["url_hash"]),
                )
                if temas:
                    actualizados += 1
                else:
                    sin_tema += 1
        pg.commit()
        log.info("Temas actualizados: %d registros", actualizados)
        if sin_tema:
            log.info("Marcadas como sin tema (se conservan por el denominador): %d", sin_tema)
    except Exception as e:
        pg.rollback()
        log.error("Error actualizando temas: %s", e, exc_info=True)
    finally:
        pg.close()
    return actualizados


def sincronizar_log(run_stats: list[dict]) -> None:
    """
    Copia el scraping_log de SQLite a Supabase.
    Solo inserta las entradas con status='ok' aún no presentes.
    """
    configurar_logging("supabase")
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


def sincronizar_observaciones(limit: Optional[int] = None) -> int:
    """
    Copia la tabla `observaciones` de SQLite a Supabase.

    Una fila por pieza vista en cada ejecución. Es lo que permite medir cuánto
    aguanta una pieza en portada y en qué posición, es decir, la duración de la
    atención además del alta. Se deduplica por (url_hash, run_id).
    """
    configurar_logging("supabase")
    sq = conectar_sqlite()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    enviadas = 0

    try:
        with pg.cursor() as cur:
            cur.execute(f"SELECT DISTINCT run_id FROM {schema}.observaciones")
            ya_en_pg = {fila[0] for fila in cur.fetchall()}

        consulta = "SELECT url_hash, medio, run_id, observado_en, posicion, fuente FROM observaciones"
        if limit:
            consulta += f" LIMIT {int(limit)}"
        filas = [dict(f) for f in sq.execute(consulta).fetchall()]
        pendientes = [f for f in filas if f["run_id"] not in ya_en_pg]

        if not pendientes:
            log.info("observaciones: nada que sincronizar")
            return 0

        insert_sql = f"""
            INSERT INTO {schema}.observaciones
                (url_hash, medio, run_id, observado_en, posicion, fuente)
            VALUES %s
            ON CONFLICT (url_hash, run_id) DO NOTHING
        """
        lote_size = 500
        for i in range(0, len(pendientes), lote_size):
            lote = pendientes[i : i + lote_size]
            valores = [
                (f["url_hash"], f["medio"], f["run_id"], f["observado_en"],
                 f["posicion"], f["fuente"])
                for f in lote
            ]
            with pg.cursor() as cur:
                psycopg2.extras.execute_values(cur, insert_sql, valores)
            pg.commit()
            enviadas += len(lote)

        log.info("observaciones: %d filas sincronizadas", enviadas)
    except Exception as e:
        pg.rollback()
        log.error("Error sincronizando observaciones: %s", e, exc_info=True)
    finally:
        sq.close()
        pg.close()

    return enviadas


def reclasificar_corpus(
    dry_run: bool = False,
    limit: Optional[int] = None,
    todas: bool = False,
) -> dict:
    """
    Reetiqueta el corpus con la versión vigente del clasificador.

    Sin esto, cada pieza conserva para siempre la etiqueta que le puso la
    versión del clasificador vigente el día que se raspó, mientras
    `config/temas.py` y las pistas siguen evolucionando. Una serie temporal de
    saliencia construida sobre un corpus así confunde el cambio de agenda con
    el cambio del instrumento de medida.

    Por defecto solo revisa las piezas cuya huella no coincide con la actual.
    Con `todas=True` revisa el corpus entero, lo que sirve para sellar por
    primera vez las piezas anteriores a esta columna.

    `dry_run` calcula la deriva y no escribe: es la forma de medir cuánto
    cambiaría el corpus antes de decidir si se reclasifica.
    """
    configurar_logging("supabase")
    version = version_clasificador()
    pg = conectar_supabase()
    schema = SUPABASE["schema"]
    stats = {
        "version": version, "revisadas": 0, "sin_cambio": 0,
        "ganan_tema": 0, "pierden_tema": 0, "cambian_tema": 0, "actualizadas": 0,
    }

    try:
        condicion = "" if todas else (
            "WHERE clasificador_version IS DISTINCT FROM %(version)s")
        consulta = f"""
            SELECT url_hash, titulo, resumen, url, temas
            FROM {schema}.noticias
            {condicion}
            ORDER BY id
            {"LIMIT " + str(int(limit)) if limit else ""}
        """
        with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(consulta, {"version": version})
            filas = cur.fetchall()

        log.info("Reclasificando %d piezas con la versión %s…", len(filas), version)
        if not filas:
            return stats

        pendientes = []
        for fila in filas:
            stats["revisadas"] += 1
            antes = set(fila["temas"] or [])
            despues_lista = clasificar(
                fila["titulo"] or "", fila["resumen"] or "", fila["url"] or "")
            despues = set(despues_lista)

            if antes == despues:
                stats["sin_cambio"] += 1
            elif not antes and despues:
                stats["ganan_tema"] += 1
            elif antes and not despues:
                stats["pierden_tema"] += 1
            else:
                stats["cambian_tema"] += 1

            pendientes.append((fila["url_hash"], despues_lista, version))

        if dry_run:
            log.info("[DRY-RUN] No se ha escrito nada.")
            return stats

        actualizar_sql = f"""
            UPDATE {schema}.noticias AS n
            SET temas = v.temas, clasificador_version = v.ver
            FROM (VALUES %s) AS v(url_hash, temas, ver)
            WHERE n.url_hash = v.url_hash
        """
        lote_size = 500
        for i in range(0, len(pendientes), lote_size):
            lote = pendientes[i : i + lote_size]
            with pg.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur, actualizar_sql, lote,
                    template="(%s::text, %s::text[], %s::text)")
            pg.commit()
            stats["actualizadas"] += len(lote)
            log.info("  ✓ %d/%d selladas", stats["actualizadas"], len(pendientes))

    except Exception as e:
        pg.rollback()
        log.error("Error reclasificando el corpus: %s", e, exc_info=True)
        raise
    finally:
        pg.close()

    return stats
