"""
Señales de refuerzo del clasificador.

`EXTRA_THEME_HINTS` cubre lenguaje periodístico que no está en las keywords de
`config/temas.py` y puntúa un poco más alto que ellas. `URL_THEME_HINTS` explota
la sección que el propio medio asigna al artículo en su URL, que es una señal
muy fiable cuando aparece.
"""

from __future__ import annotations

# Pistas adicionales para cubrir lenguaje periodistico que no estaba en las
# keywords literales originales.
EXTRA_THEME_HINTS: dict[str, tuple[str, ...]] = {
    "migracion": (
        "ruta canaria",
        "salvamento maritimo",
        "frontera sur",
    ),
    "economia": (
        "igic",
        "ipc",
        "cesta de la compra",
        "mercado laboral",
    ),
    "presupuestos": (
        "cuentas publicas",
        "marco financiero",
        "fondos europeos",
    ),
    "violencia_genero": (
        "violencia sexual",
        "agresion machista",
        "igualdad",
    ),
    "politica": (
        "clavijo",
        "diputacion del comun",
        "debate de la nacionalidad canaria",
        "gobierno central",
    ),
    "medio_ambiente": (
        "aemet",
        "temporal",
        "borrasca",
        "oleaje",
        "lluvia",
        "viento",
        "nieve",
        "terremoto",
        "terremotos",
        "sismo",
        "sismica",
        "volcan",
        "fosil",
        "botanico",
        "calima",
    ),
    "vivienda": (
        "viviendas",
        "inmueble",
        "promocion residencial",
    ),
    "sanidad": (
        "ministerio de sanidad",
        "covid persistente",
        "dependencia",
        "endometriosis",
        "salud publica",
    ),
    "salud_mental": (
        "bienestar psicologico",
        "salud emocional",
    ),
    "turismo": (
        "visitacion",
        "destino",
    ),
}


URL_THEME_HINTS: dict[str, tuple[str, ...]] = {
    "migracion": ("migraciones",),
    "economia": ("economia",),
    "presupuestos": ("presupuestos", "marco-financiero", "fondos"),
    "violencia_genero": ("igualdad", "violencia-machista", "violencia-genero"),
    "politica": ("politica", "parlamento-canario"),
    "medio_ambiente": (
        "medio-ambiente",
        "medio_ambiente",
        "ciencia-y-medio-ambiente",
        "ciencia_y_medio_ambiente",
        "tiempo-canarias",
        "patrimonio-canarias",
    ),
    "vivienda": ("vivienda", "urbanismo"),
    "sanidad": ("sanidad", "salud"),
    "salud_mental": ("salud-mental", "salud_mental"),
    "turismo": ("turismo",),
}
