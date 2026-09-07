"""
Configuración de logging, unificada.

Antes cada módulo traía su propia versión de `configurar_logging()`: dos
escribían a fichero con el nombre del logger en el formato y dos solo a consola
sin él. Esta función reproduce ambos comportamientos con un parámetro.
"""

import logging
from datetime import datetime

from observatorio.config.rutas import LOG_DIR


def configurar_logging(fichero: str | None = None) -> None:
    """
    Configura el logging raíz si la aplicación aún no lo hizo.

    `fichero`: prefijo del log en disco (p. ej. "scraper" → logs/scraper_20260907.log).
    Si es None, solo se escribe a consola.
    """
    if logging.getLogger().handlers:
        return

    if fichero is None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / f"{fichero}_{datetime.now():%Y%m%d}.log"),
        ],
    )
