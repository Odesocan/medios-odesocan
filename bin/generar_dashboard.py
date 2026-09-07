"""
generar_dashboard.py — Regenera index.html con datos de la BD local. LEGADO.

Hoy no hay nada que regenerar: index.html carga sus datos de Supabase en el
navegador. El script lo detecta y lo registra como «sin cambios».

Uso:
    python bin/generar_dashboard.py --dry-run
"""

import sys
from pathlib import Path

# Permite ejecutar este script desde cualquier directorio: añade la raíz del
# repositorio a sys.path para que `import observatorio` funcione sin instalar
# el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
from pathlib import Path

from observatorio.publicacion.dashboard import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Regenera el dashboard D3 con datos frescos")
    parser.add_argument("--output", type=Path, default=None,
                        help="Ruta de salida (por defecto sobreescribe el original)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra estadísticas sin escribir nada")
    args = parser.parse_args()
    main(output=args.output, dry_run=args.dry_run)
