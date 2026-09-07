"""
Huella de la versión del clasificador.

El problema que resuelve: las piezas se clasifican una sola vez, en el momento
de la ingesta, y nunca se reetiquetan. Mientras tanto `config/temas.py` y las
pistas de `pistas.py` van cambiando. Sin registrar qué versión etiquetó cada
pieza, una serie temporal de saliencia confunde el cambio real de agenda con el
cambio del instrumento de medida.

Por qué una huella del contenido y no el commit de git: el SHA del repositorio
cambia con cualquier modificación, aunque no toque al clasificador, y dos
piezas con SHA distinto podrían haber sido etiquetadas exactamente igual. La
huella se calcula sobre lo único que determina el resultado:

    · los temas y sus palabras clave      (config/temas.py)
    · las pistas de refuerzo y de URL     (clasificacion/pistas.py)
    · el umbral de decisión               (motor.SCORE_MINIMO)
    · el modelo de spaCy realmente cargado, o su ausencia

Dos piezas con la misma huella son comparables por construcción. El modelo
entra en la huella a propósito: sin vectores el motor degrada a palabras clave
y URL, así que clasifica distinto aunque los diccionarios sean idénticos.
"""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache

from observatorio.clasificacion import motor, normalizacion
from observatorio.clasificacion.pistas import EXTRA_THEME_HINTS, URL_THEME_HINTS
from observatorio.config.temas import TEMAS


def modelo_activo() -> str:
    """Identificador del modelo de spaCy en uso, o 'sin-modelo'."""
    nlp = normalizacion._NLP
    if nlp is None:
        return "sin-spacy"
    meta = getattr(nlp, "meta", {}) or {}
    nombre = meta.get("name")
    if not nombre:
        return "spacy-blank"
    return f"{meta.get('lang', 'es')}_{nombre}-{meta.get('version', '?')}"


def componentes_version() -> dict:
    """Lo que entra en la huella. Útil para depurar una discrepancia."""
    return {
        "temas": {
            clave: {
                "label": cfg.get("label"),
                "peso_titulo": cfg.get("peso_titulo"),
                "keywords": sorted(cfg.get("keywords", [])),
            }
            for clave, cfg in sorted(TEMAS.items())
        },
        "extra_hints": {k: sorted(v) for k, v in sorted(EXTRA_THEME_HINTS.items())},
        "url_hints": {k: sorted(v) for k, v in sorted(URL_THEME_HINTS.items())},
        # Por módulo y no por valor: `from ... import SCORE_MINIMO` fijaría el
        # escalar en el momento del import y la huella dejaría de seguir al
        # umbral real si alguien lo cambia en caliente.
        "score_minimo": motor.SCORE_MINIMO,
        "modelo": modelo_activo(),
    }


@lru_cache(maxsize=1)
def version_clasificador() -> str:
    """
    Huella estable de 12 caracteres. Cambia si y solo si puede cambiar el
    resultado de `clasificar()`.
    """
    payload = json.dumps(componentes_version(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
