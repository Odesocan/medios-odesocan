"""
Filtro de secciones: qué contenido no entra en la agenda temática.

El clasificador puntúa sobre titular, entradilla y URL, y eso genera falsos
positivos sistemáticos en secciones que nada tienen que ver con los derechos
sociales. Medido sobre el corpus histórico: un fichaje deportivo se clasifica
como `economia` por las cifras del traspaso, y la crónica de un suceso también,
por los euros que aparecen en el atestado.

Hay dos mecanismos, porque el problema tiene dos formas distintas:

1. SECCIONES_EXCLUIDAS · secciones donde NADA de lo que se publica pertenece a
   la agenda de ODESOCAN. Sus piezas se guardan igual —son denominador— pero
   con `temas` vacío.

2. TEMAS_VETADOS_POR_SECCION · secciones que SÍ publican materia de derechos
   sociales pero que además generan un tipo concreto de ruido. `sucesos` es el
   caso claro: contiene la violencia de género y buena parte de la justicia,
   así que excluirla en bloque destruiría esa cobertura, pero sus 171 piezas
   etiquetadas como `economia` y sus 65 como `turismo` son ruido.

El filtro se aplica dentro de `clasificar()`, no en el scraper, para que lo
respeten por igual la ingesta y la reclasificación del corpus. Y entra en la
huella del clasificador, porque cambia el resultado.
"""

from __future__ import annotations

# Secciones cuyo contenido nunca pertenece a la agenda de derechos sociales.
# Se comparan como subcadena contra la sección deducida de la URL.
SECCIONES_EXCLUIDAS: tuple[str, ...] = (
    "deporte",      # cubre deportes, deportes-canarias, deportes/futbol…
    "futbol",
    "baloncesto",
    "balonmano",
    "motor",
    "formula-1",
    "gente",
    "famosos",
    "television",
    "tv-",
    "cine",
    "musica",
    "moda",
    "belleza",
    "toros",
    "loteria",
    "horoscopo",
    "receta",
    "gastronomia",
    "viajes",
    "juegos",
    "pasatiempos",
    "esquelas",
    "obituario",
)

# Secciones que sí publican materia relevante, con los temas que allí no
# significan lo que el clasificador cree.
TEMAS_VETADOS_POR_SECCION: dict[str, frozenset[str]] = {
    # Las cifras del atestado disparan `economia`; los hoteles y el «turista»
    # de una crónica de sucesos disparan `turismo`. La justicia, la violencia
    # de género, la migración, la sanidad y la vivienda sí son legítimas aquí.
    "suceso": frozenset({"economia", "turismo"}),
    "tribunal": frozenset({"economia", "turismo"}),
}


def seccion_excluida(seccion: str | None) -> bool:
    """¿Pertenece la sección a un ámbito ajeno a los derechos sociales?"""
    if not seccion:
        return False
    return any(patron in seccion for patron in SECCIONES_EXCLUIDAS)


def temas_vetados(seccion: str | None) -> frozenset[str]:
    """Temas que no se admiten en esta sección, aunque el score los active."""
    if not seccion:
        return frozenset()
    vetados: set[str] = set()
    for patron, temas in TEMAS_VETADOS_POR_SECCION.items():
        if patron in seccion:
            vetados |= temas
    return frozenset(vetados)
