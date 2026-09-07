"""
construir_wordcloud.py — Recalcula el agregado medios.wordcloud_terms.

Requiere SUPABASE_URL y SUPABASE_SERVICE_ROLE_KEY (la service_role, no la anon:
el script escribe en la base y necesita saltarse RLS).

Uso:
    python bin/construir_wordcloud.py
"""

import sys
from pathlib import Path

# Permite ejecutar este script desde cualquier directorio: añade la raíz del
# repositorio a sys.path para que `import observatorio` funcione sin instalar
# el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sys

from observatorio.agregados.wordcloud import main

if __name__ == "__main__":
    # Un fallo de configuración es un mensaje de una línea, no un traceback:
    # el traceback no aporta nada cuando lo que falta es un secret.
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
