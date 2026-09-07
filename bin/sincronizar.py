"""
sincronizar.py — Vuelca la SQLite local a Supabase.

Uso:
    python bin/sincronizar.py              # sincroniza todo lo pendiente
    python bin/sincronizar.py --limit 500  # máximo de registros por ejecución
    python bin/sincronizar.py --dry-run    # muestra qué se enviaría sin escribir
"""

import sys
from pathlib import Path

# Permite ejecutar este script desde cualquier directorio: añade la raíz del
# repositorio a sys.path para que `import observatorio` funcione sin instalar
# el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from observatorio.almacenamiento.postgres import (
    actualizar_temas_vacios,
    sincronizar,
    sincronizar_log,
)
from observatorio.comun.registro import configurar_logging

if __name__ == "__main__":
    configurar_logging("supabase")
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
        actualizar_temas_vacios()

    print("\nResumen:")
    for k, v in stats.items():
        print(f"  {k}: {v}")
