"""
Rutas del proyecto.

`BASE_DIR` es la raíz del repositorio: este fichero está en
`observatorio/config/`, así que hay que subir dos niveles. De ahí cuelgan la
base SQLite, la caché de HTML y los logs, todos ignorados por git.

Los directorios se crean al importar el módulo, igual que hacía `config.py`.
"""

from pathlib import Path

BASE_DIR   = Path(__file__).resolve().parents[2]
DATA_DIR   = BASE_DIR / "data"
DB_PATH    = DATA_DIR / "noticias.db"
CACHE_DIR  = DATA_DIR / "html_cache"
LOG_DIR    = BASE_DIR / "logs"

for d in [DATA_DIR, CACHE_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
