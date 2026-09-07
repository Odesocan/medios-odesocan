"""
raspar.py — Scraping directo de uno o todos los medios, sin sync ni dashboard.

Uso:
    python bin/raspar.py                    # todos los medios
    python bin/raspar.py --medio canarias7  # solo uno
    python bin/raspar.py --dry-run          # prueba sin guardar en BD
    python bin/raspar.py --lista-medios     # inventario y salir
"""

import sys
from pathlib import Path

# Permite ejecutar este script desde cualquier directorio: añade la raíz del
# repositorio a sys.path para que `import observatorio` funcione sin instalar
# el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

from observatorio.comun.registro import configurar_logging
from observatorio.config.medios import MEDIOS
from observatorio.recoleccion.orquestador import scrapear_todos

# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    configurar_logging("scraper")
    parser = argparse.ArgumentParser(
        description="Scraper de medios canarios"
    )
    parser.add_argument(
        "--medio", "-m",
        help="ID del medio a scrapear (por defecto: todos)",
        choices=list(MEDIOS.keys()),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Prueba sin guardar en BD",
    )
    parser.add_argument(
        "--articulos", action="store_true",
        help="Extrae texto completo de cada noticia (más lento)",
    )
    parser.add_argument(
        "--lista-medios", action="store_true",
        help="Muestra los medios configurados y sale",
    )
    args = parser.parse_args()

    if args.lista_medios:
        print("\nMedios configurados:")
        for k, v in MEDIOS.items():
            feeds = len(v.get("rss", []))
            print(f"  {k:20s} — {v['nombre']} ({feeds} feeds RSS, tipo: {v['tipo']})")
        raise SystemExit(0)

    medios = [args.medio] if args.medio else None
    scrapear_todos(
        dry_run=args.dry_run,
        extraer_articulos=args.articulos,
        medios=medios,
    )
