"""
Normalización de texto para el clasificador.

Carga el modelo de spaCy una sola vez al importar. Si no hay modelo instalado
(o no trae vectores), `_HAS_VECTORS` queda a False y el motor degrada a
keywords + URL sin fallar.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from urllib.parse import unquote, urlparse

try:
    import spacy
except ImportError:  # pragma: no cover - fallback defensivo
    spacy = None


def _cargar_modelo():
    if spacy is None:
        return None
    for modelo in ("es_core_news_md", "es_core_news_sm"):
        try:
            return spacy.load(modelo, disable=["parser", "ner"])
        except OSError:
            continue
    return spacy.blank("es")


_NLP = _cargar_modelo()
_HAS_VECTORS = bool(_NLP and getattr(_NLP.vocab, "vectors_length", 0))


def _normalizar(texto: str) -> str:
    """Minúsculas + quitar tildes para comparación robusta."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _fragmentos(texto: str) -> tuple[str, ...]:
    return tuple(tok for tok in re.split(r"[^a-z0-9]+", _normalizar(texto)) if len(tok) > 2)


@lru_cache(maxsize=4096)
def _doc(texto: str):
    if not _NLP or not texto:
        return None
    return _NLP(texto)


def _tokens_texto(texto: str) -> set[str]:
    doc = _doc(texto)
    if doc is not None:
        tokens = set()
        for token in doc:
            if token.is_space or token.is_punct:
                continue
            base = token.lemma_ if token.lemma_ and token.lemma_ != "-PRON-" else token.text
            base_norm = _normalizar(base)
            if base_norm and len(base_norm) > 2 and any(ch.isalpha() for ch in base_norm):
                tokens.add(base_norm)
        if tokens:
            return tokens
    return set(_fragmentos(texto))


def _segmentos_url(url: str) -> tuple[str, ...]:
    if not url:
        return ()
    path = unquote(urlparse(url).path)
    segmentos = []
    for parte in path.split("/"):
        parte = _normalizar(parte.strip())
        parte = parte.replace("_", "-")
        if parte:
            segmentos.append(parte)
    return tuple(segmentos)
