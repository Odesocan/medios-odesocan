"""
Palabras vacías del castellano, específicas del corpus canario.

OJO: hoy NADIE importa `STOPWORDS_EXTRA`. Estaba en `config.py` sin usarse. El
pipeline de la nube de palabras mantiene su propia lista en
`observatorio/agregados/wordcloud.py` (`SPANISH_STOPWORDS`), que es la que sí
surte efecto. Se conserva aquí, visible, en lugar de enterrada.
"""
# ── Stopwords en español (complementan las de spacy/nltk) ────────────────────
STOPWORDS_EXTRA = {
    "canarias", "canario", "canaria", "isla", "islas", "tenerife",
    "gran", "palmas", "lanzarote", "fuerteventura", "gomera", "hierro",
    "palma", "año", "años", "día", "días", "vez", "veces", "hoy",
    "ayer", "mañana", "según", "tras", "ante", "bajo", "sobre",
    "parte", "través", "cabo", "junto",
}
