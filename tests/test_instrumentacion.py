"""
Comprobaciones del régimen de medida nuevo (R1–R5).

No prueban el clasificador ni los selectores de cada cabecera, que dependen de
la web real: prueban que el pipeline registra lo que el cuaderno metodológico
dice que registra. Si uno de estos tests se pone en rojo, alguna serie deja de
ser calculable.

    python -m unittest discover -s tests -v
"""

import importlib.util
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import scraper                                   # noqa: E402
from clasificador import CLASIFICADOR_VERSION, version_clasificador   # noqa: E402
from config import SCRAPER                       # noqa: E402


# Los titulares son largos a propósito: el parser descarta los enlaces de
# navegación por su falta de cuerpo, y un fixture con titulares de tres
# palabras no probaría lo que dice probar.
PORTADA = """
<html><body>
  <article><h2><a href="/vivienda/2026/09/07/ayudas-alquiler.html">El Gobierno aprueba las ayudas al alquiler para 2027</a></h2></article>
  <article><h2><a href="/deportes/2026/09/07/tenerife-liga.html">El Tenerife gana en el descuento y se coloca líder</a></h2></article>
  <article><h2><a href="/sanidad/2026-09-06/listas-espera.html">Las listas de espera crecen un 12% en un año</a></h2></article>
  <article><h2><a href="/festival-de-cine.html">Un nuevo festival de cine llega a la capital en octubre</a></h2></article>
</body></html>
"""

ARTICULO = """
<html><head>
  <script type="application/ld+json">
    {"@type": "NewsArticle", "datePublished": "2026-09-07T08:30:00+01:00"}
  </script>
</head><body><article>
  <p>El Gobierno aprueba una linea de ayudas al alquiler para los hogares con
     mayor esfuerzo residencial, segun anuncio la consejeria esta manana.</p>
  <p>La medida se suma al parque publico de vivienda anunciado en julio y se
     tramitara por la via de urgencia durante el proximo trimestre.</p>
</article></body></html>
"""

MEDIO_PRUEBA = {
    "nombre": "Diario de Prueba",
    "url": "https://prueba.es/",
    "tipo": "html_only",
    "rss": [],
    "color": "#000000",
    "selectores": {"titular": "h2 a"},
}

# Etiquetado determinista: lo que se prueba aquí es el pipeline, no el criterio
# del clasificador, que depende de si spaCy tiene vectores cargados.
TEMAS_FIJOS = {
    "https://prueba.es/vivienda/2026/09/07/ayudas-alquiler.html": ["vivienda"],
    "https://prueba.es/sanidad/2026-09-06/listas-espera.html": ["sanidad"],
}


class ClienteFalso(scraper.ClienteHTTP):
    """Cliente que sirve HTML de prueba y anota cada petición."""

    def __init__(self):
        self.peticiones = []

    def get(self, url, usar_cache=True, es_feed=False):
        self.peticiones.append({"url": url, "usar_cache": usar_cache})
        if url.rstrip("/") == "https://prueba.es":
            return PORTADA
        return ARTICULO

    def close(self):
        pass


def clasificar_falso(titulo="", resumen="", url=""):
    return list(TEMAS_FIJOS.get(url, []))


class BaseTirada(unittest.TestCase):
    """Ejecuta una tirada completa contra un medio de mentira."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "prueba.db"
        self.conn = scraper.init_db(self.db)
        self.cliente = ClienteFalso()

        self._medios_original = dict(scraper.MEDIOS)
        scraper.MEDIOS["prueba"] = MEDIO_PRUEBA
        self._clasificar_original = scraper.clasificar
        scraper.clasificar = clasificar_falso
        self._presupuesto_original = SCRAPER["texto_full_por_tirada"]

    def tearDown(self):
        scraper.clasificar = self._clasificar_original
        scraper.MEDIOS.clear()
        scraper.MEDIOS.update(self._medios_original)
        SCRAPER["texto_full_por_tirada"] = self._presupuesto_original
        self.conn.close()
        self.tmp.cleanup()

    def tirada(self, run_id="tirada-1", conocidos=None, articulos=True):
        return scraper.scrapear_medio(
            "prueba", self.conn, self.cliente,
            extraer_articulos=articulos, run_id=run_id,
            conocidos=conocidos or set(),
        )

    def noticias(self):
        return [dict(f) for f in self.conn.execute(
            "SELECT * FROM noticias ORDER BY url"
        ).fetchall()]

    def observaciones(self):
        return [dict(f) for f in self.conn.execute(
            "SELECT * FROM observaciones ORDER BY posicion, run_id"
        ).fetchall()]


class R1Denominador(BaseTirada):

    def test_las_piezas_sin_tema_se_guardan(self):
        stats = self.tirada()
        guardadas = self.noticias()
        self.assertEqual(len(guardadas), 4, "las cuatro piezas del listado entran")
        self.assertEqual(stats["sin_tema"], 2)

        sin_tema = [n for n in guardadas if json.loads(n["temas"]) == []]
        self.assertEqual(len(sin_tema), 2, "el denominador se conserva")

    def test_las_piezas_sin_tema_no_gastan_descarga(self):
        self.tirada()
        descargados = [p["url"] for p in self.cliente.peticiones if p["url"] != "https://prueba.es/"]
        self.assertEqual(len(descargados), 2, "solo se descarga el cuerpo de las piezas con tema")
        for url in descargados:
            self.assertIn(url, TEMAS_FIJOS)

    def test_el_presupuesto_de_texto_completo_se_respeta(self):
        SCRAPER["texto_full_por_tirada"] = 1
        stats = self.tirada()
        self.assertEqual(stats["textos"], 1)
        con_texto = [n for n in self.noticias() if n["texto_full"]]
        self.assertEqual(len(con_texto), 1)


class R2Observaciones(BaseTirada):

    def test_cada_pieza_del_listado_deja_observacion(self):
        stats = self.tirada()
        obs = self.observaciones()
        self.assertEqual(len(obs), 4)
        self.assertEqual(stats["observadas"], 4)
        self.assertEqual([o["posicion"] for o in obs], [1, 2, 3, 4])
        self.assertTrue(all(o["fuente"] == "html" for o in obs))

    def test_una_pieza_ya_conocida_sigue_observandose(self):
        """
        Es lo que mide la duración de la atención: la pieza no se da de alta dos
        veces, pero cada tirada que sigue en portada deja su marca.
        """
        self.tirada(run_id="tirada-1")
        conocidos = {scraper.url_hash(n["url"]) for n in self.noticias()}
        stats = self.tirada(run_id="tirada-2", conocidos=conocidos)

        self.assertEqual(stats["nuevas"], 0, "ninguna alta nueva")
        self.assertEqual(stats["observadas"], 4, "pero sí cuatro observaciones")
        self.assertEqual(len(self.noticias()), 4)
        self.assertEqual(len(self.observaciones()), 8)

    def test_la_misma_tirada_no_duplica_observaciones(self):
        self.tirada(run_id="tirada-1")
        self.tirada(run_id="tirada-1")
        self.assertEqual(len(self.observaciones()), 4)

    def test_el_listado_no_se_sirve_de_cache(self):
        """Una portada cacheada fabricaría permanencia falsa."""
        self.tirada()
        portada = [p for p in self.cliente.peticiones if p["url"] == "https://prueba.es/"]
        self.assertTrue(portada)
        self.assertFalse(portada[0]["usar_cache"])


class R3VersionClasificador(BaseTirada):

    def test_cada_pieza_se_sella(self):
        self.tirada()
        for noticia in self.noticias():
            self.assertEqual(noticia["clasificador_version"], CLASIFICADOR_VERSION)

    def test_la_huella_es_estable_y_tiene_forma(self):
        self.assertEqual(version_clasificador(), CLASIFICADOR_VERSION)
        partes = CLASIFICADOR_VERSION.split("-")
        self.assertTrue(partes[0].startswith("v"))
        self.assertEqual(len(partes[1]), 12, "huella de configuración de 12 caracteres")


class R4FechaYProcedencia(unittest.TestCase):

    def test_fecha_embebida_en_la_url(self):
        casos = {
            "https://x.es/canarias/2026/09/07/pieza.html": "2026-09-07",
            "https://x.es/tenerife/2026-09-04/pieza.html": "2026-09-04",
            "https://x.es/politica/20260907143012-pieza.html": "2026-09-07",
        }
        for url, dia in casos.items():
            self.assertTrue(scraper.fecha_desde_url(url).startswith(dia), url)

    def test_una_ruta_sin_fecha_no_inventa_ninguna(self):
        self.assertIsNone(scraper.fecha_desde_url("https://x.es/pieza-12345.html"))
        self.assertIsNone(scraper.fecha_desde_url("https://x.es/2026/13/40/imposible.html"))
        self.assertIsNone(scraper.fecha_desde_url("https://x.es/1998/01/02/demasiado-vieja.html"))

    def test_fecha_desde_el_articulo(self):
        fecha, origen = scraper.fecha_desde_html(ARTICULO)
        self.assertEqual(origen, scraper.ORIGEN_JSONLD)
        self.assertTrue(fecha.startswith("2026-09-07T07:30"), fecha)

        meta = '<html><head><meta property="article:published_time" content="2026-09-05T10:00:00Z"></head></html>'
        fecha, origen = scraper.fecha_desde_html(meta)
        self.assertEqual(origen, scraper.ORIGEN_META)

        etiqueta_time = '<html><body><time datetime="2026-09-03T09:15:00+00:00">3 sep</time></body></html>'
        fecha, origen = scraper.fecha_desde_html(etiqueta_time)
        self.assertEqual(origen, scraper.ORIGEN_TIME)

        self.assertEqual(scraper.fecha_desde_html("<html></html>"), (None, None))

    def test_la_precision_de_dia_no_se_confunde_con_la_hora_exacta(self):
        self.assertNotIn(scraper.ORIGEN_URL, scraper.ORIGENES_HORA_EXACTA)
        self.assertIn(scraper.ORIGEN_RSS, scraper.ORIGENES_HORA_EXACTA)

    def test_seccion_desde_la_url(self):
        self.assertEqual(scraper.seccion_desde_url("https://x.es/vivienda/2026/09/07/p.html"), "vivienda")
        self.assertEqual(scraper.seccion_desde_url("https://x.es/amp/sanidad/p.html"), "sanidad")
        self.assertIsNone(scraper.seccion_desde_url("https://x.es/pieza-suelta.html"))


class R4EnLaTirada(BaseTirada):

    def test_cada_pieza_declara_de_donde_sale_su_fecha(self):
        self.tirada()
        por_url = {n["url"]: n for n in self.noticias()}

        # Con tema: se descarga el artículo, así que gana la hora exacta.
        con_tema = por_url["https://prueba.es/vivienda/2026/09/07/ayudas-alquiler.html"]
        self.assertEqual(con_tema["fecha_pub_origen"], scraper.ORIGEN_JSONLD)

        # Sin tema pero con fecha en la ruta: precisión de día, sin gastar nada.
        del_denominador = por_url["https://prueba.es/deportes/2026/09/07/tenerife-liga.html"]
        self.assertEqual(del_denominador["fecha_pub_origen"], scraper.ORIGEN_URL)
        self.assertTrue(del_denominador["fecha_pub"].startswith("2026-09-07"))

        # Sin fecha en ninguna parte: sintética, y declarada como tal.
        sin_nada = por_url["https://prueba.es/festival-de-cine.html"]
        self.assertEqual(sin_nada["fecha_pub_origen"], scraper.ORIGEN_SINTETICO)

    def test_la_seccion_se_registra(self):
        self.tirada()
        secciones = {n["seccion"] for n in self.noticias()}
        self.assertIn("vivienda", secciones)
        self.assertIn("deportes", secciones)


def _cargar_wordcloud():
    ruta = RAIZ / "scripts" / "build_wordcloud_terms.py"
    spec = importlib.util.spec_from_file_location("build_wordcloud_terms", ruta)
    modulo = importlib.util.module_from_spec(spec)
    # El módulo tiene que estar en sys.modules antes de ejecutarlo: @dataclass
    # busca ahí el espacio de nombres de la clase.
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


class R5CorteTemporal(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.wc = _cargar_wordcloud()

    def _noticia(self, idx, periodo, texto):
        return self.wc.NewsItem(
            record_id=str(idx), medio="prueba", temas=("vivienda",),
            titulo=texto, resumen=texto, texto_full=texto, periodo=periodo,
        )

    def test_el_mes_sale_de_la_marca_de_raspado(self):
        self.assertEqual(self.wc.mes_de("2026-09-07T10:00:00+00:00"), "2026-09")
        self.assertEqual(self.wc.mes_de(None), "")
        self.assertEqual(self.wc.mes_de("basura"), "")

    def test_el_acumulado_y_el_corte_mensual_conviven(self):
        items = [self._noticia(i, "2026-08", "alquiler turistico vivienda") for i in range(5)]
        items += [self._noticia(10 + i, "2026-09", "desahucio alquiler vivienda") for i in range(5)]

        acumulado = self.wc.build_aggregates(items, self.wc.PERIODO_ACUMULADO)
        agosto = self.wc.build_aggregates(
            [i for i in items if i.periodo == "2026-08"], "2026-08"
        )
        self.assertTrue(acumulado and agosto)
        self.assertTrue(all(f["periodo"] == "__all__" for f in acumulado))
        self.assertTrue(all(f["periodo"] == "2026-08" for f in agosto))

        # La clave primaria de la tabla es (periodo, scope_key, gram_type,
        # normalized_term): sin el periodo, el corte pisaría al acumulado.
        clave = lambda f: (f["periodo"], f["scope_key"], f["gram_type"], f["normalized_term"])
        todas = acumulado + agosto
        self.assertEqual(len(todas), len({clave(f) for f in todas}))

    def test_los_ambitos_mensuales_diminutos_se_descartan(self):
        items = [self._noticia(i, "2026-09", "vivienda alquiler") for i in range(2)]
        self.assertEqual(self.wc.build_aggregates(items, "2026-09"), [])
        self.assertTrue(self.wc.build_aggregates(items, self.wc.PERIODO_ACUMULADO))

    def test_se_conservan_como_mucho_doce_meses(self):
        items = [
            self._noticia(i, f"2025-{mes:02d}", "vivienda alquiler")
            for i, mes in enumerate(range(1, 13))
        ] + [self._noticia(100, "2026-01", "vivienda alquiler")]
        meses = self.wc.meses_a_construir(items)
        self.assertEqual(len(meses), self.wc.MONTHS_KEPT)
        self.assertEqual(meses[-1], "2026-01", "se quedan los más recientes")


class MigracionLocal(unittest.TestCase):

    def test_una_bd_antigua_se_migra_sola(self):
        """La BD local de una versión anterior no debe romper la tirada."""
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "vieja.db"
            vieja = sqlite3.connect(ruta)
            vieja.execute("""
                CREATE TABLE noticias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT NOT NULL UNIQUE, url_hash TEXT NOT NULL UNIQUE,
                    medio TEXT NOT NULL, titulo TEXT NOT NULL, resumen TEXT,
                    texto_full TEXT, fecha_pub TEXT, fecha_scrap TEXT NOT NULL,
                    fuente TEXT NOT NULL, raw_json TEXT, temas TEXT)
            """)
            vieja.commit()
            vieja.close()

            conn = scraper.init_db(ruta)
            columnas = {f[1] for f in conn.execute("PRAGMA table_info(noticias)").fetchall()}
            self.assertIn("fecha_pub_origen", columnas)
            self.assertIn("clasificador_version", columnas)
            self.assertIn("seccion", columnas)
            tablas = {f[0] for f in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            self.assertIn("observaciones", tablas)
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)


class DenominadorLimpio(unittest.TestCase):
    """
    Desde R1 nada se descarta, así que lo que entra en el listado es el
    denominador. Un enlace de navegación colado ahí deflacta todas las cuotas.
    """

    def test_los_enlaces_de_navegacion_no_son_piezas(self):
        for basura in ("Ver más", "Sucesos", "Última hora", "Leer", ""):
            self.assertFalse(scraper._es_titular(basura), basura)
        for titular in (
            "Valverde renueva el mobiliario de los tanatorios municipales",
            "Muere un hombre en La Frontera",
        ):
            self.assertTrue(scraper._es_titular(titular), titular)

    def test_la_portada_los_filtra(self):
        html = """
        <html><body>
          <h2><a href="/sucesos/">Sucesos</a></h2>
          <h2><a href="/p1.html">Ver más</a></h2>
          <h2><a href="/vivienda/2026/09/07/una-pieza-de-verdad.html">
              El Cabildo aprueba el plan de vivienda para 2027</a></h2>
        </body></html>
        """

        class Cliente(scraper.ClienteHTTP):
            def __init__(self):
                pass

            def get(self, url, usar_cache=True, es_feed=False):
                return html

        piezas = scraper.parsear_html_portada("prueba", MEDIO_PRUEBA, Cliente())
        self.assertEqual(len(piezas), 1)
        self.assertEqual(piezas[0]["posicion"], 1)


class FechasDeFeed(unittest.TestCase):
    """El feed da hora exacta, pero no siempre da una fecha creíble."""

    def test_una_fecha_absurda_del_feed_no_se_marca_como_real(self):
        self.assertIsNone(scraper._iso_o_none("1970-01-01T00:00:00+00:00"))
        self.assertIsNone(scraper._iso_o_none("no es una fecha"))
        self.assertIsNone(scraper._iso_o_none(None))
        self.assertTrue(scraper._iso_o_none("2026-09-07T08:30:00Z").startswith("2026-09-07"))

    def test_las_marcas_con_zulu_se_normalizan_a_utc(self):
        self.assertEqual(
            scraper._iso_o_none("2026-09-07T10:00:00Z"),
            scraper._iso_o_none("2026-09-07T12:00:00+02:00"),
        )
