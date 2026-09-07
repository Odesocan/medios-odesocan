"""
Configuración del observatorio.

Este subpaquete reúne todo lo que se edita para cambiar QUÉ se observa, sin
tocar la lógica. Cada módulo cubre una decisión distinta:

    rutas.py        dónde viven la base local, la caché y los logs
    medios.py       las 17 cabeceras que se raspan
    temas.py        los 15 temas y sus diccionarios de palabras clave
    scraping.py     ritmo de las peticiones y pool de User-Agents
    secciones.py    qué secciones quedan fuera de la agenda temática
    credenciales.py conexión a Supabase (todo por variable de entorno)
    stopwords.py    palabras vacías del castellano

Se re-exporta todo aquí para que el resto del código pueda escribir
`from observatorio.config import MEDIOS, TEMAS` sin conocer la subdivisión.
"""

from observatorio.config.credenciales import SUPABASE
from observatorio.config.medios import MEDIOS
from observatorio.config.secciones import SECCIONES_EXCLUIDAS, TEMAS_VETADOS_POR_SECCION
from observatorio.config.rutas import BASE_DIR, CACHE_DIR, DATA_DIR, DB_PATH, LOG_DIR
from observatorio.config.scraping import SCRAPER, USER_AGENTS
from observatorio.config.stopwords import STOPWORDS_EXTRA
from observatorio.config.temas import TEMAS

__all__ = [
    "BASE_DIR", "CACHE_DIR", "DATA_DIR", "DB_PATH", "LOG_DIR",
    "MEDIOS", "TEMAS", "SCRAPER", "USER_AGENTS", "SUPABASE", "STOPWORDS_EXTRA",
    "SECCIONES_EXCLUIDAS", "TEMAS_VETADOS_POR_SECCION",
]
