"""
Clasificación temática de noticias.

    pistas.py         señales de refuerzo: lenguaje periodístico y rutas de URL
    normalizacion.py  minúsculas, tildes, lemas y tokens (spaCy si está)
    motor.py          la puntuación y el umbral: `clasificar()`

No es un modelo entrenado: es un sistema de puntuación híbrido que suma cuatro
señales (keywords literales, lemas, segmentos de URL y similitud vectorial).
"""
