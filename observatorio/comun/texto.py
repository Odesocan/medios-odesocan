"""
Helpers de texto compartidos entre la recolección y el almacenamiento.
"""

import hashlib

from bs4 import BeautifulSoup

def url_hash(url: str) -> str:
    """Identificador estable de una URL: SHA-256 truncado a 16 caracteres."""
    return hashlib.sha256(url.strip().encode()).hexdigest()[:16]

def limpiar_html(texto: str) -> str:
    """Elimina etiquetas HTML de un fragmento de texto."""
    if not texto:
        return ""
    soup = BeautifulSoup(texto, "html.parser")
    return soup.get_text(separator=" ", strip=True)
