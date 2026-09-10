#!/usr/bin/env python3
"""
reclasificar.py — Sella el corpus con la versión del clasificador y mide su deriva (R3).

Dos piezas etiquetadas con clasificadores distintos no son comparables en una
serie temporal. El corpus histórico se escribió sin dejar constancia de con qué
clasificador se etiquetó: `clasificador_version` está a NULL en todas esas
piezas, y mientras siga así cualquier serie que las cruce con las nuevas mezcla
dos instrumentos.

Este script arregla las dos cosas a la vez: vuelve a pasar el clasificador
actual por el corpus y sella cada pieza con su huella. De paso mide cuánto se
ha movido el instrumento, que es una cifra interesante por sí misma.

Uso:
    python scripts/reclasificar.py                    # modo seco: mide, no escribe
    python scripts/reclasificar.py --aplicar          # escribe temas y versión
    python scripts/reclasificar.py --solo-sin-sellar  # solo el tramo antiguo
    python scripts/reclasificar.py --medio canarias7 --limit 500

El modo seco es el de por defecto a propósito: conviene saber cuánta deriva hay
antes de sobrescribir las etiquetas con las que se han publicado cifras.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2.extras   # noqa: E402

from clasificador import CLASIFICADOR_VERSION, _HAS_VECTORS, clasificar  # noqa: E402
from config import SUPABASE  # noqa: E402
from supabase_loader import conectar_supabase  # noqa: E402

log = logging.getLogger("reclasificar")

LOTE = 500


def leer_corpus(pg, solo_sin_sellar: bool, medio: str | None, limit: int | None) -> list[dict]:
    """Lee las piezas a reclasificar con lo que necesita el clasificador."""
    schema = SUPABASE["schema"]
    condiciones = []
    params: list[object] = []
    if solo_sin_sellar:
        condiciones.append("clasificador_version IS NULL")
    if medio:
        condiciones.append("medio = %s")
        params.append(medio)
    where = f"WHERE {' AND '.join(condiciones)}" if condiciones else ""
    sql = f"""
        SELECT url_hash, medio, titulo, resumen, url, temas, clasificador_version
        FROM {schema}.noticias
        {where}
        ORDER BY fecha_scrap ASC
        {"LIMIT %s" if limit else ""}
    """
    if limit:
        params.append(limit)
    with pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return [dict(fila) for fila in cur.fetchall()]


def medir_deriva(filas: list[dict]) -> tuple[list[tuple[str, list[str]]], dict]:
    """
    Reclasifica en memoria y compara con lo que había.

    Devuelve los cambios a escribir y un resumen de la deriva. «Deriva» aquí es
    cuántas piezas cambian de etiqueta al pasarles el clasificador de hoy: si es
    alta, las cifras publicadas con el etiquetado anterior no son comparables
    con las nuevas, y hay que decirlo en la ficha técnica.
    """
    cambios: list[tuple[str, list[str]]] = []
    resumen = {
        "procesadas": len(filas),
        "sin_sellar": 0,
        "identicas": 0,
        "distintas": 0,
        "ganan_tema": 0,
        "pierden_todo": 0,
        "temas_anadidos": Counter(),
        "temas_retirados": Counter(),
    }

    for fila in filas:
        if not fila["clasificador_version"]:
            resumen["sin_sellar"] += 1
        antes = list(fila["temas"] or [])
        ahora = clasificar(fila["titulo"] or "", fila["resumen"] or "", fila["url"] or "")
        cambios.append((fila["url_hash"], ahora))

        if set(antes) == set(ahora):
            resumen["identicas"] += 1
            continue

        resumen["distintas"] += 1
        if not antes and ahora:
            resumen["ganan_tema"] += 1
        if antes and not ahora:
            resumen["pierden_todo"] += 1
        for tema in set(ahora) - set(antes):
            resumen["temas_anadidos"][tema] += 1
        for tema in set(antes) - set(ahora):
            resumen["temas_retirados"][tema] += 1

    return cambios, resumen


def escribir(pg, cambios: list[tuple[str, list[str]]]) -> int:
    """Escribe temas y versión del clasificador, por lotes."""
    schema = SUPABASE["schema"]
    escritas = 0
    sql = f"""
        UPDATE {schema}.noticias AS n
        SET temas = datos.temas, clasificador_version = datos.version
        FROM (VALUES %s) AS datos (url_hash, temas, version)
        WHERE n.url_hash = datos.url_hash
    """
    for i in range(0, len(cambios), LOTE):
        lote = [
            (url_hash, temas, CLASIFICADOR_VERSION)
            for url_hash, temas in cambios[i : i + LOTE]
        ]
        with pg.cursor() as cur:
            psycopg2.extras.execute_values(
                cur, sql, lote, template="(%s, %s::text[], %s)"
            )
        pg.commit()
        escritas += len(lote)
        log.info("  selladas %d/%d", escritas, len(cambios))
    return escritas


def informe(resumen: dict, aplicado: bool) -> None:
    procesadas = max(resumen["procesadas"], 1)
    print()
    print(f"Clasificador actual: {CLASIFICADOR_VERSION}")
    print(f"Piezas procesadas:   {resumen['procesadas']}")
    print(f"  sin sellar antes:  {resumen['sin_sellar']}")
    print(f"  etiqueta idéntica: {resumen['identicas']} "
          f"({100.0 * resumen['identicas'] / procesadas:.1f} %)")
    print(f"  etiqueta distinta: {resumen['distintas']} "
          f"({100.0 * resumen['distintas'] / procesadas:.1f} %)  ← deriva")
    print(f"    ganan tema:      {resumen['ganan_tema']}")
    print(f"    pierden todo:    {resumen['pierden_todo']}")

    if resumen["temas_anadidos"]:
        print("\n  Temas que gana el corpus:")
        for tema, n in resumen["temas_anadidos"].most_common(10):
            print(f"    +{n:5d}  {tema}")
    if resumen["temas_retirados"]:
        print("\n  Temas que pierde el corpus:")
        for tema, n in resumen["temas_retirados"].most_common(10):
            print(f"    -{n:5d}  {tema}")

    print()
    if aplicado:
        print("Escrito. El corpus queda sellado con la versión de arriba.")
    else:
        print("Modo seco: no se ha escrito nada. Para aplicarlo, --aplicar.")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="Reclasifica y sella el corpus (R3)")
    parser.add_argument("--aplicar", action="store_true",
                        help="Escribe los cambios. Sin esto solo mide la deriva.")
    parser.add_argument("--solo-sin-sellar", action="store_true",
                        help="Solo las piezas con clasificador_version a NULL")
    parser.add_argument("--medio", help="Limitar a una cabecera")
    parser.add_argument("--limit", type=int, help="Máximo de piezas a procesar")
    parser.add_argument("--forzar-sin-modelo", action="store_true",
                        help="Permite escribir aunque spaCy no tenga vectores")
    args = parser.parse_args()

    # Sin vectores, el clasificador pierde la señal semántica y etiqueta
    # distinto. Sellar el corpus desde una máquina sin el modelo dejaría una
    # huella que no se corresponde con la del pipeline en producción.
    if args.aplicar and not _HAS_VECTORS and not args.forzar_sin_modelo:
        print(
            "spaCy no tiene vectores cargados: el etiquetado no sería el mismo "
            "que en el pipeline.\nInstala el modelo con\n"
            "    python -m spacy download es_core_news_md\n"
            "o repite con --forzar-sin-modelo si de verdad quieres sellar así.",
            file=sys.stderr,
        )
        return 2

    pg = conectar_supabase()
    try:
        filas = leer_corpus(pg, args.solo_sin_sellar, args.medio, args.limit)
        if not filas:
            print("No hay piezas que reclasificar con esos filtros.")
            return 0
        log.info("Reclasificando %d piezas…", len(filas))
        cambios, resumen = medir_deriva(filas)
        if args.aplicar:
            escribir(pg, cambios)
        informe(resumen, aplicado=args.aplicar)
    finally:
        pg.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
