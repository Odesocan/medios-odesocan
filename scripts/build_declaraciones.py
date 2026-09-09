#!/usr/bin/env python3
"""
Detecta declaraciones de cargos públicos en las noticias de Supabase.

Lee `medios.noticias`, pasa cada pieza por `declaraciones.py` y deja el
resultado en dos destinos:

- `medios.declaraciones`   — una fila por declaración, en estado `pendiente`.
- `medios.actores_candidatos` — emisores agregados, para curar el censo.

Sobre la escritura en `medios.declaraciones`: el upsert manda **sólo las
columnas de detección**. Las de revisión (`estado`, `veredicto`, `fuentes`,
`revisado_por`…) no viajan en el payload, así que PostgREST no las toca. Un
reproceso del corpus completo actualiza las detecciones y deja intacto el
trabajo humano: lo descartado sigue descartado y lo publicado sigue publicado.

Uso:
    python scripts/build_declaraciones.py                 # corpus completo
    python scripts/build_declaraciones.py --dias 30       # sólo lo reciente
    python scripts/build_declaraciones.py --dry-run -n 20 # sin escribir nada
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

from supabase import Client, create_client

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from declaraciones import extraer_declaraciones, resumen_actor  # noqa: E402

SOURCE_SCHEMA = os.getenv("SUPABASE_SOURCE_SCHEMA", "medios")
SOURCE_TABLE = os.getenv("SUPABASE_SOURCE_TABLE", "noticias")
TARGET_SCHEMA = os.getenv("SUPABASE_TARGET_SCHEMA", "medios")
TARGET_TABLE = os.getenv("DECLARACIONES_TABLE", "declaraciones")
CANDIDATOS_TABLE = os.getenv("DECLARACIONES_CANDIDATOS_TABLE", "actores_candidatos")

BATCH_SIZE = int(os.getenv("SUPABASE_BATCH_SIZE", "1000"))
UPSERT_CHUNK_SIZE = int(os.getenv("DECLARACIONES_UPSERT_CHUNK_SIZE", "500"))

# Umbral de entrada a la tabla. Por debajo hay sobre todo verbos neutros sin
# ningún anclaje: ruido que sólo engordaría la cola.
MIN_PRIORIDAD = int(os.getenv("DECLARACIONES_MIN_PRIORIDAD", "25"))

# La reclasificación temática de cada cita carga spaCy y es la parte cara del
# proceso. Se puede desactivar para una pasada rápida sobre todo el histórico:
# los temas de la noticia y el área del cargo se siguen aplicando igual.
CLASIFICAR_CITA = os.getenv("DECLARACIONES_CLASIFICAR_CITA", "1") not in ("0", "false", "no")

SOURCE_COLUMNS = [
    "id", "url", "url_hash", "medio", "titulo", "resumen",
    "texto_full", "fecha_pub", "temas",
]

# Columnas que escribe el pipeline. Se declaran de forma explícita para que
# quede por escrito qué NO se toca: todo lo que no esté en esta lista pertenece
# a la revisión humana.
COLUMNAS_DETECCION = [
    "hash_declaracion", "url_hash", "url", "medio", "fecha_pub",
    "cita", "tipo_cita", "actor_texto", "actor_nombre", "actor_slug",
    "cargo", "cargo_completo", "area", "ambito", "institucion", "ex_cargo",
    "verbo", "verbo_lema", "fuerza", "marcadores", "temas", "campo",
    "contexto", "prioridad", "verificable",
]


def get_client() -> Client:
    faltan = [
        nombre
        for nombre in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")
        if not os.getenv(nombre)
    ]
    if faltan:
        raise RuntimeError(
            "Faltan variables de entorno obligatorias: "
            + ", ".join(faltan)
            + ". Se configuran como secrets del repositorio en "
            "Settings → Secrets and variables → Actions. "
            "SUPABASE_SERVICE_ROLE_KEY debe ser la service_role key del "
            "proyecto, no la anon key."
        )
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])


def fetch_noticias(client: Client, dias: int = 0, limite: int = 0) -> list[dict]:
    """Descarga las noticias a procesar, paginando la API.

    `dias` acota a lo publicado recientemente. Es lo que usa la ejecución
    diaria: el corpus completo sólo hace falta al reprocesar tras un cambio en
    el detector.
    """
    filas: list[dict] = []
    offset = 0
    corte = None
    if dias > 0:
        corte = (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat()

    while True:
        query = (
            client.schema(SOURCE_SCHEMA)
            .table(SOURCE_TABLE)
            .select(",".join(SOURCE_COLUMNS))
            .order("id", desc=True)
            .range(offset, offset + BATCH_SIZE - 1)
        )
        if corte:
            query = query.gte("fecha_pub", corte)

        lote = query.execute().data or []
        if not lote:
            break
        filas.extend(lote)

        if limite and len(filas) >= limite:
            return filas[:limite]
        if len(lote) < BATCH_SIZE:
            break
        offset += BATCH_SIZE

    return filas


def construir_filas(noticias: Sequence[dict]) -> tuple[list[dict], list[dict], Counter]:
    """Extrae las declaraciones y arma las filas de ambas tablas."""
    filas: list[dict] = []
    todas = []
    stats: Counter = Counter()

    for noticia in noticias:
        stats["noticias"] += 1
        detectadas = extraer_declaraciones(noticia, clasificar_cita=CLASIFICAR_CITA)
        for decl in detectadas:
            stats["detectadas"] += 1
            if decl.prioridad < MIN_PRIORIDAD:
                stats["bajo_umbral"] += 1
                continue
            todas.append(decl)
            stats[f"fuerza:{decl.fuerza}"] += 1
            if decl.verificable:
                stats["verificables"] += 1
            filas.append({k: v for k, v in decl.to_row().items() if k in COLUMNAS_DETECCION})

    # Una misma declaración puede venir de dos noticias distintas sólo si el
    # url_hash coincide, cosa imposible; aun así el upsert exige claves únicas
    # dentro del lote, así que se deduplica antes de enviarlas.
    por_hash = {fila["hash_declaracion"]: fila for fila in filas}
    stats["duplicadas"] = len(filas) - len(por_hash)

    candidatos = [
        {**entrada, "generado_en": datetime.now(timezone.utc).isoformat()}
        for entrada in resumen_actor(todas)
    ]
    return list(por_hash.values()), candidatos, stats


def chunked(items: Sequence[dict], size: int) -> Iterable[Sequence[dict]]:
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def upsert_declaraciones(client: Client, filas: Sequence[dict]) -> None:
    """Escribe las detecciones sin pisar la revisión humana.

    PostgREST actualiza en el conflicto sólo las columnas presentes en el
    payload, y el payload no lleva ninguna columna de revisión. Ése es todo el
    mecanismo que protege el trabajo del equipo.
    """
    for lote in chunked(filas, UPSERT_CHUNK_SIZE):
        (
            client.schema(TARGET_SCHEMA)
            .table(TARGET_TABLE)
            .upsert(list(lote), on_conflict="hash_declaracion")
            .execute()
        )


def reconstruir_candidatos(client: Client, filas: Sequence[dict]) -> None:
    """Rehace el agregado de emisores desde cero.

    Se reconstruye entero, y no por upsert, porque es un recuento: si un cargo
    deja de aparecer, su fila tiene que desaparecer, no quedarse con el último
    número que tuvo.
    """
    client.rpc("truncate_actores_candidatos", {}).execute()
    for lote in chunked(filas, UPSERT_CHUNK_SIZE):
        (
            client.schema(TARGET_SCHEMA)
            .table(CANDIDATOS_TABLE)
            .upsert(list(lote), on_conflict="actor_slug")
            .execute()
        )


def informar(stats: Counter, filas: Sequence[dict], candidatos: Sequence[dict]) -> None:
    print(f"Noticias procesadas ....... {stats['noticias']}")
    print(f"Declaraciones detectadas .. {stats['detectadas']}")
    print(f"  bajo umbral (<{MIN_PRIORIDAD}) ...... {stats['bajo_umbral']}")
    print(f"  guardadas ............... {len(filas)}")
    print(f"  verificables ............ {stats['verificables']}")
    print(f"Emisores distintos ........ {len(candidatos)}")
    reparto = sorted(
        ((k.split(":", 1)[1], v) for k, v in stats.items() if k.startswith("fuerza:")),
        key=lambda kv: kv[1], reverse=True,
    )
    if reparto:
        print("Reparto por fuerza asertiva:")
        for fuerza, n in reparto:
            print(f"  {fuerza:<12} {n}")


def previsualizar(filas: Sequence[dict], cuantas: int) -> None:
    """Muestra la cabecera de la cola sin escribir en la base de datos."""
    top = sorted(filas, key=lambda f: f["prioridad"], reverse=True)[:cuantas]
    for fila in top:
        actor = fila["actor_nombre"] or fila["cargo_completo"] or fila["actor_texto"]
        print(f"\n[{fila['prioridad']:3d}] {fila['fuerza']:<11} {fila['medio']}")
        print(f"      {actor} — {fila['cargo_completo'] or 'sin cargo explícito'}")
        print(f"      «{fila['cita'][:150]}»")
        print(f"      marcadores: {', '.join(fila['marcadores']) or '—'} | temas: {', '.join(fila['temas']) or '—'}")
        print(f"      {fila['url']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Detector de declaraciones de cargos públicos")
    parser.add_argument("--dias", type=int, default=int(os.getenv("DECLARACIONES_DIAS", "0")),
                        help="Procesar sólo noticias de los últimos N días (0 = todas)")
    parser.add_argument("-n", "--limite", type=int, default=0,
                        help="Máximo de noticias a leer. Para pruebas.")
    parser.add_argument("--dry-run", action="store_true",
                        help="No escribe en Supabase: informa y muestra la cabecera de la cola")
    args = parser.parse_args()

    client = get_client()
    noticias = fetch_noticias(client, dias=args.dias, limite=args.limite)
    if not noticias:
        print("No se recuperaron noticias desde Supabase.", file=sys.stderr)
        return 1

    filas, candidatos, stats = construir_filas(noticias)
    informar(stats, filas, candidatos)

    if args.dry_run:
        print("\n— DRY RUN: no se ha escrito nada —")
        previsualizar(filas, 15)
        return 0

    if not filas:
        print("Ninguna declaración supera el umbral. Nada que escribir.")
        return 0

    upsert_declaraciones(client, filas)
    reconstruir_candidatos(client, candidatos)
    print(f"\n✓ {len(filas)} declaraciones sincronizadas, {len(candidatos)} emisores agregados.")
    return 0


if __name__ == "__main__":
    # Un fallo de configuración es un mensaje de una línea, no un traceback.
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
