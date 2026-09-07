"""
Helpers de texto compartidos entre la recolección y el almacenamiento.
"""

import hashlib
import re
from urllib.parse import urlparse

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


_SEG_FECHA = re.compile(r"^\d{2,4}([-_]\d{2}([-_]\d{2})?)?$")


def seccion_desde_url(url: str) -> str | None:
    """
    Sección que el propio medio asigna al artículo, leída de la ruta de la URL.

    Se toman los primeros segmentos alfabéticos hasta topar con uno que parezca
    fecha o número, que es donde suele empezar el identificador de la pieza:

        canarias7.es/politica/2026/09/07/slug.html      → politica
        eldiario.es/canariasahora/migraciones/x_1_2.html → canariasahora/migraciones
        efe.com/canarias/2026-09-04/slug                 → canarias

    Es un dato del medio, no del clasificador: sirve para contrastar los 15 temas
    de ODESOCAN contra la taxonomía nativa de cada cabecera.
    """
    if not url:
        return None
    partes = []
    for seg in urlparse(url).path.strip("/").split("/"):
        if not seg or _SEG_FECHA.match(seg) or seg.isdigit():
            break
        if "." in seg:            # el último segmento es ya el fichero del artículo
            break
        # Un segmento largo y muy troceado es el slug de la pieza, no una sección
        # (hay medios que cuelgan los artículos de la raíz).
        if len(seg) > 40 or seg.count("-") > 4:
            break
        partes.append(seg.lower())
        if len(partes) == 2:
            break
    return "/".join(partes) or None
