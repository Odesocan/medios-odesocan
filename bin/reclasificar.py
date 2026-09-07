"""
reclasificar.py — Reetiqueta el corpus con la versión vigente del clasificador.

Cada pieza se clasifica una sola vez, al raspar. Mientras tanto los temas y las
pistas van cambiando, así que un corpus sin reclasificar mezcla etiquetas de
versiones distintas del instrumento y arruina cualquier comparación
longitudinal.

Uso:
    python bin/reclasificar.py --version     # muestra la huella actual y sale
    python bin/reclasificar.py --dry-run     # mide la deriva sin escribir
    python bin/reclasificar.py               # reclasifica lo desactualizado
    python bin/reclasificar.py --todas       # revisa el corpus entero
    python bin/reclasificar.py --limit 500   # acota la tirada
"""

import sys
from pathlib import Path

# Permite ejecutar este script desde cualquier directorio: añade la raíz del
# repositorio a sys.path para que `import observatorio` funcione sin instalar
# el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from observatorio.clasificacion.version import componentes_version, version_clasificador
from observatorio.comun.registro import configurar_logging


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reclasifica el corpus con la versión vigente del clasificador")
    parser.add_argument("--version", action="store_true",
                        help="Muestra la huella del clasificador actual y sale")
    parser.add_argument("--dry-run", action="store_true",
                        help="Calcula la deriva sin escribir nada")
    parser.add_argument("--todas", action="store_true",
                        help="Revisa el corpus entero, no solo lo desactualizado")
    parser.add_argument("--limit", type=int, default=None,
                        help="Máximo de piezas a revisar")
    args = parser.parse_args()

    configurar_logging("supabase")

    if args.version:
        c = componentes_version()
        print(f"Versión del clasificador: {version_clasificador()}")
        print(f"  temas:        {len(c['temas'])}")
        print(f"  umbral:       {c['score_minimo']}")
        print(f"  modelo spaCy: {c['modelo']}")
        return 0

    # Se importa aquí para que `--version` no necesite psycopg2 ni credenciales.
    from observatorio.almacenamiento.postgres import reclasificar_corpus

    stats = reclasificar_corpus(dry_run=args.dry_run, limit=args.limit, todas=args.todas)

    print(f"\nVersión del clasificador: {stats['version']}")
    print(f"  piezas revisadas:      {stats['revisadas']}")
    print(f"    · sin cambio:        {stats['sin_cambio']}")
    print(f"    · ganan tema:        {stats['ganan_tema']}")
    print(f"    · pierden tema:      {stats['pierden_tema']}")
    print(f"    · cambian de tema:   {stats['cambian_tema']}")
    print(f"  piezas actualizadas:   {stats['actualizadas']}")

    if stats["revisadas"]:
        deriva = 100 * (stats["revisadas"] - stats["sin_cambio"]) / stats["revisadas"]
        print(f"\n  Deriva del instrumento: {deriva:.1f}% de las piezas revisadas")
        print("  cambiarían de etiqueta con la versión actual.")
    if args.dry_run:
        print("\n  [DRY-RUN] No se ha escrito nada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
