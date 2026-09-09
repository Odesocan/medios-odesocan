"""
Pruebas del detector de declaraciones.

El detector alimenta una cola de verificación humana, así que el error caro no
es dejar escapar una declaración: es atribuir a alguien algo que no dijo. Las
pruebas de falsos positivos (`test_no_atribuye_*`) cubren esa parte y son las
que no deberían relajarse al ajustar umbrales.

Los nombres de persona que aparecen aquí son ficticios.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from declaraciones import (  # noqa: E402
    Declaracion,
    calcular_prioridad,
    detectar_actores,
    detectar_marcadores,
    es_verificable,
    extraer_declaraciones,
    resumen_actor,
    tema_por_area,
)


def noticia(titulo="", resumen="", texto_full="", temas=(), url_hash="h"):
    return {
        "titulo": titulo, "resumen": resumen, "texto_full": texto_full,
        "temas": list(temas), "medio": "Medio de prueba",
        "url": "https://ejemplo.test/noticia", "url_hash": url_hash,
        "fecha_pub": "2026-09-01T08:00:00Z",
    }


def extraer(**kwargs) -> list[Declaracion]:
    # `clasificar_cita=False` mantiene las pruebas deterministas y sin spaCy.
    return extraer_declaraciones(noticia(**kwargs), clasificar_cita=False)


# ── Identificación de cargos ─────────────────────────────────────────────────

def test_cargo_autonomico_con_area():
    (actor, _, _), = detectar_actores("la consejera de Sanidad compareció")
    assert actor.cargo == "Consejería"
    assert actor.cargo_completo == "consejera de Sanidad"
    assert actor.ambito == "autonomico"
    assert actor.area == "sanidad"


def test_la_institucion_manda_sobre_el_ambito_por_defecto():
    """Un consejero de cabildo es insular aunque el núcleo del cargo sea el
    mismo que el de un consejero del Gobierno de Canarias."""
    (actor, _, _), = detectar_actores("el consejero de Educación del Cabildo de Tenerife")
    assert actor.ambito == "insular"
    assert actor.institucion == "Cabildo de Tenerife"


def test_cargo_municipal():
    (actor, _, _), = detectar_actores("la alcaldesa de Arrecife anunció")
    assert actor.ambito == "municipal"
    assert actor.cargo_completo == "alcaldesa de Arrecife"


def test_nombre_en_aposicion_pospuesta():
    texto = "El presidente del Cabildo de La Palma, Andrés Melián Cabrera, compareció ayer"
    (actor, _, _), = detectar_actores(texto)
    assert actor.nombre == "Andrés Melián Cabrera"


def test_nombre_en_aposicion_antepuesta():
    texto = "Lucía Ferrera Botín, consejera de Bienestar Social, defendió el plan"
    (actor, _, _), = detectar_actores(texto)
    assert actor.nombre == "Lucía Ferrera Botín"


def test_ex_cargo_se_marca():
    (actor, _, _), = detectar_actores("el ex consejero de Economía")
    assert actor.ex_cargo is True


def test_el_complemento_no_termina_en_conector():
    (actor, _, _), = detectar_actores("la consejera de la casa")
    assert not actor.cargo_completo.rstrip().endswith(("de", "del", "de la"))


def test_el_sintagma_no_arrastra_puntuacion():
    (actor, _, _), = detectar_actores("según el consejero de Sanidad del Cabildo de Gran Canaria.")
    assert not actor.texto.endswith((".", ","))


# ── Las cuatro formas de atribución ──────────────────────────────────────────

def test_titular_con_dos_puntos():
    d, = extraer(titulo='Ferrera: "Canarias ha reducido las listas de espera un 12% en un año"')
    assert d.tipo_cita == "titular"
    assert d.actor.nombre == "Ferrera"
    assert d.cita == "Canarias ha reducido las listas de espera un 12% en un año"
    assert d.verificable is True


def test_estilo_indirecto():
    d, = extraer(titulo="La consejera de Sanidad asegura que hay 400 camas nuevas en la red")
    assert d.tipo_cita == "indirecta"
    assert d.verbo_lema == "asegurar"
    assert d.fuerza == "asercion"
    assert d.cita == "hay 400 camas nuevas en la red"


def test_cita_directa_con_atribucion_pospuesta():
    d, = extraer(
        titulo="Empleo",
        resumen='La consejera de Empleo, Marta Ruiz Delgado, aseguró que "el paro ha caído un 8,4%".',
    )
    assert d.tipo_cita == "directa"
    assert d.actor.nombre == "Marta Ruiz Delgado"
    assert d.cita == "el paro ha caído un 8,4%"


def test_atribucion_con_segun():
    d, = extraer(
        titulo="Salud mental",
        resumen="Las urgencias psiquiátricas crecieron un 30% en dos años, "
                "según el consejero de Sanidad.",
    )
    assert d.tipo_cita == "pospuesta"
    assert d.cita == "Las urgencias psiquiátricas crecieron un 30% en dos años"


def test_sujeto_elidido_se_recupera_de_la_frase_anterior():
    """`"…", aseguró.` — el emisor está en la frase previa, como al leerlo."""
    ds = extraer(
        titulo="Acogida",
        texto_full='El presidente del Cabildo de Tenerife compareció ayer. '
                   '"Ningún menor se quedará en la calle", aseguró.',
    )
    directa = [d for d in ds if d.tipo_cita == "directa"]
    assert directa, "no se recuperó el sujeto elidido"
    assert directa[0].actor.institucion == "Cabildo de Tenerife"


# ── Falsos positivos: lo que no debe entrar en la cola ───────────────────────

def test_no_atribuye_una_cita_al_cargo_de_la_frase_siguiente():
    """El error más caro: poner en boca de alguien lo que dijo otro."""
    ds = extraer(
        titulo="Paro",
        resumen='La consejera de Empleo aseguró que "el paro ha caído un 8,4%". '
                'El alcalde de Arrecife criticó la medida.',
    )
    assert all("alcalde" not in d.actor.texto.lower() for d in ds)


def test_no_atribuye_encabezados_de_seccion():
    assert extraer(titulo="Canarias: las claves de la semana en el Parlamento") == []
    assert extraer(titulo='Sanidad: el "efecto llamada" no existe, dicen los expertos') == []


def test_no_atribuye_apellido_suelto_sin_comillas():
    """Sin comillas, un token suelto es indistinguible de una etiqueta de
    sección, y la lista de etiquetas nunca estará completa."""
    assert extraer(titulo="Melián: la situación del empleo no mejora en las islas") == []


def test_no_confunde_entrecomillado_de_matiz_con_declaracion():
    """`el "efecto llamada"` es un entrecomillado de matiz, no una afirmación."""
    ds = extraer(
        titulo="Migración",
        resumen='El consejero de Migración habló del "efecto llamada" en su comparecencia.',
    )
    assert all(len(d.cita.split()) >= 4 for d in ds)


def test_texto_sin_cargos_no_produce_declaraciones():
    assert extraer(
        titulo="El tiempo en Canarias",
        resumen="La Aemet prevé lluvias débiles en el norte de las islas de mayor relieve.",
    ) == []


# ── Fuerza asertiva y verificabilidad ────────────────────────────────────────

def test_una_valoracion_no_es_verificable():
    d, = extraer(
        titulo="Paro",
        resumen="El consejero de Economía lamentó que la situación laboral no mejore.",
    )
    assert d.fuerza == "valoracion"
    assert d.verificable is False


def test_una_demanda_no_es_verificable():
    d, = extraer(
        titulo="Vivienda",
        resumen="La consejera de Vivienda exigió que el Estado transfiera los fondos pendientes.",
    )
    assert d.fuerza == "demanda"
    assert d.verificable is False


def test_un_compromiso_es_verificable_aunque_no_lleve_cifras():
    """Una promesa se puede seguir en el tiempo aunque no traiga número."""
    assert es_verificable("compromiso", []) is True
    assert es_verificable("asercion", []) is False
    assert es_verificable("asercion", ["porcentaje"]) is True


def test_marcadores_detectados():
    marcadores = detectar_marcadores(
        "Canarias es la primera comunidad en listas de espera, con 45.000 pacientes, un 12% más que en 2025"
    )
    assert {"porcentaje", "ranking", "unidad_publica", "comparacion"} <= set(marcadores)


def test_sin_anclaje_no_hay_marcadores():
    assert detectar_marcadores("Trabajamos para mejorar la vida de la gente") == []


# ── Prioridad ────────────────────────────────────────────────────────────────

def test_la_asercion_con_cifras_prioriza_sobre_la_valoracion():
    alta, = extraer(titulo='Ferrera: "El paro ha bajado un 12% este año en Canarias"')
    baja, = extraer(
        titulo="Paro",
        resumen="El consejero de Economía lamentó que la situación laboral no mejore.",
    )
    assert alta.prioridad > baja.prioridad


def test_el_ex_cargo_resta_prioridad():
    actual, = extraer(
        titulo="Sanidad",
        resumen="El consejero de Sanidad aseguró que hay 400 camas nuevas en la red pública.",
    )
    anterior, = extraer(
        titulo="Sanidad",
        resumen="El ex consejero de Sanidad aseguró que hay 400 camas nuevas en la red pública.",
    )
    assert anterior.prioridad < actual.prioridad


def test_prioridad_acotada_a_cien():
    d, = extraer(
        titulo='Marta Ruiz Delgado: "Canarias es la primera comunidad de España en listas '
               'de espera, con 45.000 pacientes, un 32% más que en 2025 y nunca antes visto"',
    )
    assert 0 <= d.prioridad <= 100


# ── Trazabilidad y agregación ────────────────────────────────────────────────

def test_el_hash_es_estable_entre_ejecuciones():
    """Reprocesar el corpus no puede duplicar filas ni perder la revisión ya
    hecha por una persona."""
    primera, = extraer(titulo='Ferrera: "El paro ha bajado un 12% este año en Canarias"')
    segunda, = extraer(titulo='Ferrera: "El paro ha bajado un 12% este año en Canarias"')
    assert primera.hash_declaracion == segunda.hash_declaracion


def test_el_hash_distingue_declaraciones_distintas():
    a, = extraer(titulo='Ferrera: "El paro ha bajado un 12% este año en Canarias"')
    b, = extraer(titulo='Ferrera: "El paro ha subido un 12% este año en Canarias"')
    assert a.hash_declaracion != b.hash_declaracion


def test_la_fila_lleva_la_trazabilidad_a_la_noticia():
    d, = extraer(titulo='Ferrera: "El paro ha bajado un 12% este año en Canarias"')
    fila = d.to_row()
    assert fila["url_hash"] == "h"
    assert fila["url"] == "https://ejemplo.test/noticia"
    assert fila["medio"] == "Medio de prueba"
    assert fila["fecha_pub"] == "2026-09-01T08:00:00Z"


def test_el_area_del_cargo_aporta_tema():
    """Si habla la consejera de Sanidad, la declaración es de sanidad aunque la
    cita no repita la palabra."""
    d, = extraer(
        titulo="Presupuestos",
        resumen="La consejera de Sanidad aseguró que hay 400 camas nuevas en la red pública.",
        temas=["presupuestos"],
    )
    assert "sanidad" in d.temas
    assert "presupuestos" in d.temas


def test_tema_por_area():
    assert tema_por_area("salud mental") == "salud_mental"
    assert tema_por_area("empleo") == "economia"
    assert tema_por_area("cultura") == ""      # área real sin tema en el observatorio


def test_resumen_actor_agrega_por_emisor():
    ds = extraer(
        titulo="Sanidad",
        texto_full="La consejera de Sanidad aseguró que hay 400 camas nuevas en la red pública. "
                   "La consejera de Sanidad prometió que abrirá dos centros más este año.",
    )
    agregado = resumen_actor(ds)
    assert len(agregado) == 1
    assert agregado[0]["n_declaraciones"] == 2
    assert agregado[0]["n_verificables"] == 2


# ── Robustez de entrada ──────────────────────────────────────────────────────

def test_entidades_html_sin_decodificar():
    """Parte del corpus llega con entidades crudas; sin decodificarlas los
    regex de comillas fallan y las citas salen con `&oacute;` incrustado."""
    d, = extraer(
        titulo="Empleo",
        resumen="La consejera de Empleo asegur&oacute; que la situaci&oacute;n "
                "mejor&oacute; un 8% este a&ntilde;o.",
    )
    assert "&" not in d.cita
    assert "porcentaje" in d.marcadores


@pytest.mark.parametrize("campos", [
    {}, {"titulo": None}, {"resumen": None}, {"texto_full": None},
])
def test_campos_vacios_o_nulos_no_revientan(campos):
    base = noticia()
    base.update(campos)
    assert extraer_declaraciones(base, clasificar_cita=False) == []


def test_prioridad_no_es_negativa():
    from declaraciones import _Candidato, Actor
    cand = _Candidato(cita="x", tipo_cita="indirecta",
                      actor=Actor(texto="ex consejero", ex_cargo=True), fuerza="demanda")
    assert calcular_prioridad(cand, []) >= 0


# ── Filtro de sintagmas nominales ────────────────────────────────────────────

def test_acepta_asercion_con_verbo_fuera_de_la_lista_de_formas():
    """El detector de formas finitas es estrecho a propósito; la longitud es la
    segunda vía para no perder afirmaciones buenas."""
    d, = extraer(
        titulo="Vivienda",
        resumen='La consejera de Vivienda aseguró: "esta ley perjudica a las familias isleñas".',
    )
    assert d.cita == "esta ley perjudica a las familias isleñas"


def test_rechaza_entrecomillado_nominal_corto():
    ds = extraer(
        titulo="Migración",
        resumen='El consejero de Migración negó el "efecto llamada" en la comparecencia.',
    )
    assert all('efecto llamada' != d.cita for d in ds)
