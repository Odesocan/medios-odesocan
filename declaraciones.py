"""
declaraciones.py — Detector de declaraciones de cargos públicos.

Localiza en el corpus de prensa canaria los pasajes donde **una persona con
responsabilidad institucional afirma algo**, los normaliza y los deja en una
cola de trabajo. No emite veredictos: no dice si lo afirmado es cierto, falso o
engañoso. Esa parte es humana y ocurre fuera de este módulo.

Lo que sí hace:

  1. Identifica al emisor por su **cargo** (`la consejera de Sanidad`,
     `el alcalde de Arrecife`), que es un patrón estable, y no por una lista de
     nombres que habría que mantener a mano. Si el nombre aparece en aposición
     junto al cargo (`el presidente de Canarias, Fulano de Tal, aseguró…`) lo
     recoge, y así el registro de actores se construye desde el propio corpus.
  2. Extrae la declaración en sus cuatro formas habituales en prensa: titular
     con dos puntos, cita entrecomillada, estilo indirecto (`X aseguró que…`) y
     atribución pospuesta (`…, según X`).
  3. Clasifica la **fuerza asertiva** del verbo introductorio. Una aserción
     factual (`cifra`, `asegura`, `niega`) es verificable; una valoración
     (`lamenta`, `celebra`) o una demanda (`exige`) no lo es. Esta distinción
     es la que separa el trabajo de verificación del ruido.
  4. Marca los **anclajes verificables** de la propia cita: cifras, porcentajes,
     magnitudes, comparaciones, rankings, plazos y cuantificadores absolutos.
     Una afirmación sin ninguno de estos anclajes rara vez se puede contrastar.

El resultado es una lista de `Declaracion` ordenable por prioridad editorial.
"""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator, Sequence

# ──────────────────────────────────────────────────────────────────────────────
# 1. Cargos públicos
# ──────────────────────────────────────────────────────────────────────────────
# Se detecta el núcleo del cargo y después se expande el complemento hacia la
# derecha ("consejera" → "consejera de Sanidad del Gobierno de Canarias"). Un
# único regex monolítico para todo el sintagma sería ilegible y frágil; separar
# núcleo y expansión permite probar las dos mitades por separado.

# núcleo → (etiqueta canónica, ámbito por defecto)
CARGOS_NUCLEO: dict[str, tuple[str, str]] = {
    # --- autonómico ---
    "presidente":            ("Presidencia", "autonomico"),
    "presidenta":            ("Presidencia", "autonomico"),
    "vicepresidente":        ("Vicepresidencia", "autonomico"),
    "vicepresidenta":        ("Vicepresidencia", "autonomico"),
    "consejero":             ("Consejería", "autonomico"),
    "consejera":             ("Consejería", "autonomico"),
    "viceconsejero":         ("Viceconsejería", "autonomico"),
    "viceconsejera":         ("Viceconsejería", "autonomico"),
    "director general":      ("Dirección General", "autonomico"),
    "directora general":     ("Dirección General", "autonomico"),
    "diputado":              ("Diputación parlamentaria", "autonomico"),
    "diputada":              ("Diputación parlamentaria", "autonomico"),
    "portavoz":              ("Portavocía", "autonomico"),
    "diputado del común":    ("Diputación del Común", "autonomico"),
    "diputada del común":    ("Diputación del Común", "autonomico"),
    # --- insular ---
    "consejero insular":     ("Consejería insular", "insular"),
    "consejera insular":     ("Consejería insular", "insular"),
    # --- municipal ---
    "alcalde":               ("Alcaldía", "municipal"),
    "alcaldesa":             ("Alcaldía", "municipal"),
    "concejal":              ("Concejalía", "municipal"),
    "concejala":             ("Concejalía", "municipal"),
    "edil":                  ("Concejalía", "municipal"),
    "teniente de alcalde":   ("Tenencia de alcaldía", "municipal"),
    # --- estatal con competencia en Canarias ---
    "delegado del gobierno": ("Delegación del Gobierno", "estatal"),
    "delegada del gobierno": ("Delegación del Gobierno", "estatal"),
    "ministro":              ("Ministerio", "estatal"),
    "ministra":              ("Ministerio", "estatal"),
    "secretario de estado":  ("Secretaría de Estado", "estatal"),
    "secretaria de estado":  ("Secretaría de Estado", "estatal"),
    "senador":               ("Senaduría", "estatal"),
    "senadora":              ("Senaduría", "estatal"),
    # --- orgánico de partido: no es cargo público, pero habla en su nombre ---
    "secretario general":    ("Secretaría general", "partido"),
    "secretaria general":    ("Secretaría general", "partido"),
    "coordinador general":   ("Coordinación general", "partido"),
    "coordinadora general":  ("Coordinación general", "partido"),
}

# Ordenados de más largo a más corto: "consejero insular" debe ganar a
# "consejero", y "secretario de estado" a "secretario general".
_NUCLEOS_ORDENADOS = sorted(CARGOS_NUCLEO, key=len, reverse=True)

RE_CARGO = re.compile(
    r"(?<![\wáéíóúñü])"
    r"(?:(?P<det>el|la|los|las|un|una)\s+)?"
    r"(?P<ex>ex\s*-?\s*)?"
    r"(?P<nucleo>" + "|".join(re.escape(n) for n in _NUCLEOS_ORDENADOS) + r")"
    r"(?![\wáéíóúñü])",
    re.IGNORECASE,
)

# Instituciones que fijan el ámbito con independencia del núcleo del cargo.
# "el consejero de Educación del Cabildo de Tenerife" es insular, no autonómico.
INSTITUCIONES: tuple[tuple[str, str, str], ...] = (
    # (patrón normalizado, institución canónica, ámbito)
    ("gobierno de canarias",        "Gobierno de Canarias",        "autonomico"),
    ("parlamento de canarias",      "Parlamento de Canarias",      "autonomico"),
    ("cabildo de tenerife",         "Cabildo de Tenerife",         "insular"),
    ("cabildo de gran canaria",     "Cabildo de Gran Canaria",     "insular"),
    ("cabildo de lanzarote",        "Cabildo de Lanzarote",        "insular"),
    ("cabildo de fuerteventura",    "Cabildo de Fuerteventura",    "insular"),
    ("cabildo de la palma",         "Cabildo de La Palma",         "insular"),
    ("cabildo de la gomera",        "Cabildo de La Gomera",        "insular"),
    ("cabildo de el hierro",        "Cabildo de El Hierro",        "insular"),
    ("cabildo insular",             "Cabildo insular",             "insular"),
    ("cabildo",                     "Cabildo",                     "insular"),
    ("ayuntamiento",                "Ayuntamiento",                "municipal"),
    ("gobierno de españa",          "Gobierno de España",          "estatal"),
    ("gobierno central",            "Gobierno de España",          "estatal"),
)

# Áreas de gestión. Sirven para dos cosas: cerrar el complemento del cargo con
# criterio y enrutar la declaración al tema del observatorio.
AREAS_CARGO: dict[str, str] = {
    "sanidad": "sanidad",
    "salud": "sanidad",
    "salud publica": "sanidad",
    "salud mental": "salud_mental",
    "educacion": "",
    "universidades": "",
    "empleo": "economia",
    "trabajo": "economia",
    "economia": "economia",
    "economia conocimiento y empleo": "economia",
    "hacienda": "presupuestos",
    "hacienda y presupuestos": "presupuestos",
    "presupuestos": "presupuestos",
    "vivienda": "vivienda",
    "obras publicas": "vivienda",
    "urbanismo": "vivienda",
    "bienestar social": "cuidados",
    "derechos sociales": "cuidados",
    "servicios sociales": "cuidados",
    "politica social": "cuidados",
    "dependencia": "dependencia_discapacidad",
    "discapacidad": "dependencia_discapacidad",
    "igualdad": "igualdad",
    "diversidad": "diversidad",
    "juventud": "",
    "infancia": "",
    "migracion": "migracion",
    "migraciones": "migracion",
    "turismo": "turismo",
    "transicion ecologica": "medio_ambiente",
    "medio ambiente": "medio_ambiente",
    "lucha contra el cambio climatico": "medio_ambiente",
    "agricultura": "",
    "ganaderia y pesca": "",
    "justicia": "justicia",
    "seguridad": "justicia",
    "administraciones publicas": "",
    "politica territorial": "",
    "presidencia": "",
    "cultura": "",
    "deportes": "",
    "transportes": "",
    "industria": "",
}

# Conectores admitidos dentro del complemento de un cargo.
_CONECTORES = {"de", "del", "de la", "de los", "de las", "en", "para", "y", "e", "la", "el", "los", "las"}

# ──────────────────────────────────────────────────────────────────────────────
# 2. Verbos declarativos, por fuerza asertiva
# ──────────────────────────────────────────────────────────────────────────────
# La fuerza decide si la declaración entra o no en la cola de verificación.
#   asercion   → afirma un hecho contrastable. Es el material de fact-checking.
#   compromiso → promete una acción futura. Material de seguimiento de promesas.
#   prediccion → pronostica. Verificable, pero sólo cuando llegue la fecha.
#   valoracion → juicio de valor. No verificable.
#   demanda    → exige o pide. No verificable.
#   neutro     → introduce habla sin comprometer al hablante.

VERBOS_POR_FUERZA: dict[str, tuple[str, ...]] = {
    "asercion": (
        "afirmar", "asegurar", "sostener", "mantener", "negar", "desmentir",
        "confirmar", "cifrar", "calcular", "estimar", "cuantificar", "situar",
        "revelar", "desvelar", "reconocer", "admitir", "constatar", "acreditar",
        "demostrar", "atribuir", "achacar", "acusar", "denunciar", "alegar",
        "esgrimir", "insistir", "recordar", "puntualizar", "precisar", "matizar",
        "aclarar", "rechazar", "descartar", "zanjar", "sentenciar", "replicar",
    ),
    "compromiso": (
        "prometer", "garantizar", "anunciar", "adelantar", "avanzar",
        "comprometer", "asumir", "aprobar", "firmar",
    ),
    "prediccion": (
        "prever", "augurar", "vaticinar", "pronosticar", "anticipar", "advertir",
        "alertar", "avisar",
    ),
    "valoracion": (
        "criticar", "censurar", "lamentar", "celebrar", "aplaudir", "reprochar",
        "cuestionar", "ironizar", "defender", "justificar", "valorar",
    ),
    "demanda": (
        "exigir", "reclamar", "pedir", "proponer", "plantear", "instar",
        "solicitar", "urgir",
    ),
    "neutro": (
        "decir", "declarar", "senalar", "señalar", "indicar", "apuntar",
        "explicar", "comentar", "manifestar", "expresar", "anadir", "añadir",
        "agregar", "concluir", "subrayar", "destacar", "recalcar", "remarcar",
        "enfatizar", "argumentar", "responder", "contestar", "abogar",
    ),
}

# Formas irregulares que el generador regular no acierta.
_IRREGULARES: dict[str, tuple[str, ...]] = {
    "decir":       ("dice", "dijo", "decía", "decia", "dicen", "dijeron"),
    "sostener":    ("sostiene", "sostuvo", "sostenía", "sostenia", "sostienen", "sostuvieron"),
    "mantener":    ("mantiene", "mantuvo", "mantenía", "mantenia", "mantienen", "mantuvieron"),
    "negar":       ("niega", "negó", "nego", "negaba", "niegan", "negaron"),
    "reconocer":   ("reconoce", "reconoció", "reconocio", "reconocía", "reconocen", "reconocieron"),
    "prever":      ("prevé", "preve", "previó", "previo", "preveía", "prevén", "preven"),
    "advertir":    ("advierte", "advirtió", "advirtio", "advertía", "advierten", "advirtieron"),
    "defender":    ("defiende", "defendió", "defendio", "defendía", "defienden", "defendieron"),
    "insistir":    ("insiste", "insistió", "insistio", "insistía", "insisten", "insistieron"),
    "exigir":      ("exige", "exigió", "exigio", "exigía", "exigen", "exigieron"),
    "concluir":    ("concluye", "concluyó", "concluyo", "concluía", "concluyen", "concluyeron"),
    "atribuir":    ("atribuye", "atribuyó", "atribuyo", "atribuía", "atribuyen"),
    "situar":      ("sitúa", "situa", "situó", "situo", "situaba", "sitúan", "situan"),
    "recordar":    ("recuerda", "recordó", "recordo", "recordaba", "recuerdan", "recordaron"),
    "demostrar":   ("demuestra", "demostró", "demostro", "demostraba", "demuestran"),
    "comprometer": ("se compromete", "se comprometió", "se comprometio", "se comprometen"),
    "aprobar":     ("aprueba", "aprobó", "aprobo", "aprobaba", "aprueban", "aprobaron"),
    "senalar":     ("señala", "senala", "señaló", "senalo", "señalaba", "señalan"),
    "anadir":      ("añade", "anade", "añadió", "anadio", "añadía", "añaden"),
}


def _conjugar(infinitivo: str) -> tuple[str, ...]:
    """Genera las formas verbales que aparecen en prensa: 3ª persona,
    singular y plural, en presente, indefinido e imperfecto."""
    if infinitivo in _IRREGULARES:
        return _IRREGULARES[infinitivo]
    if infinitivo.endswith("ar"):
        raiz = infinitivo[:-2]
        return (raiz + "a", raiz + "ó", raiz + "o", raiz + "aba",
                raiz + "an", raiz + "aron")
    raiz = infinitivo[:-2]
    return (raiz + "e", raiz + "ió", raiz + "io", raiz + "ía", raiz + "ia",
            raiz + "en", raiz + "ieron")


# forma conjugada → (infinitivo, fuerza)
FORMAS_VERBALES: dict[str, tuple[str, str]] = {}
for _fuerza, _infinitivos in VERBOS_POR_FUERZA.items():
    for _inf in _infinitivos:
        for _forma in _conjugar(_inf):
            FORMAS_VERBALES.setdefault(_forma.lower(), (_inf, _fuerza))

_FORMAS_ORDENADAS = sorted(FORMAS_VERBALES, key=len, reverse=True)
RE_VERBO = re.compile(
    r"(?<![\wáéíóúñü])(?P<verbo>" + "|".join(re.escape(f) for f in _FORMAS_ORDENADAS) + r")(?![\wáéíóúñü])",
    re.IGNORECASE,
)

# Prioridad editorial por fuerza. Una promesa incumplida es tan noticiable como
# un dato falso, de ahí que `compromiso` puntúe casi como `asercion`.
PESO_FUERZA = {
    "asercion": 34,
    "compromiso": 30,
    "prediccion": 22,
    "neutro": 16,
    "valoracion": 6,
    "demanda": 6,
}

FUERZAS_VERIFICABLES = frozenset({"asercion", "compromiso", "prediccion"})

# ──────────────────────────────────────────────────────────────────────────────
# 3. Anclajes verificables dentro de la cita
# ──────────────────────────────────────────────────────────────────────────────
# Sin uno de estos, una afirmación casi nunca se puede contrastar contra una
# fuente primaria: es opinión, intención o generalidad.

MARCADORES: dict[str, re.Pattern] = {
    "porcentaje": re.compile(r"\d+(?:[.,]\d+)?\s*(?:%|por\s+ciento)", re.IGNORECASE),
    "cifra": re.compile(r"(?<![\w./-])\d{1,3}(?:[.\s]\d{3})+(?![\w/])|(?<![\w./-])\d{2,}(?![\w%/.-])"),
    "magnitud": re.compile(
        r"\b(?:millones?|miles?|millardos?|euros?|€|millones\s+de\s+euros)\b", re.IGNORECASE),
    "unidad_publica": re.compile(
        r"\b(?:plazas?|camas?|viviendas?|empleos?|puestos?\s+de\s+trabajo|"
        r"profesionales|sanitarios?|docentes|pacientes|usuarios?|beneficiari[oa]s?|"
        r"listas?\s+de\s+espera|d[ií]as?\s+de\s+espera|menores|solicitudes)\b", re.IGNORECASE),
    "ranking": re.compile(
        r"\b(?:primera?\s+(?:comunidad|regi[oó]n|provincia)|a\s+la\s+cabeza|a\s+la\s+cola|"
        r"por\s+(?:encima|debajo)\s+de\s+la\s+media|l[ií]der|el\s+(?:mayor|menor|peor|mejor|m[aá]s\s+alto|m[aá]s\s+bajo)|"
        r"la\s+(?:mayor|menor|peor|mejor|m[aá]s\s+alta|m[aá]s\s+baja)|r[eé]cord|m[aá]ximo\s+hist[oó]rico|"
        r"m[ií]nimo\s+hist[oó]rico)\b", re.IGNORECASE),
    "comparacion": re.compile(
        r"\b(?:m[aá]s\s+que|menos\s+que|el\s+doble|la\s+mitad|el\s+triple|"
        r"respecto\s+a|frente\s+a|comparad[oa]\s+con|en\s+comparaci[oó]n)\b", re.IGNORECASE),
    "plazo": re.compile(
        r"\b(?:antes\s+de(?:\s+(?:que|final|fin))?|a\s+(?:finales|principios|mediados)\s+de|"
        r"en\s+(?:los\s+)?pr[oó]ximos?\s+\w+|de\s+aqu[ií]\s+a|este\s+a[ñn]o|el\s+a[ñn]o\s+que\s+viene|"
        r"en\s+20\d{2}|para\s+20\d{2}|primer\s+trimestre|segundo\s+semestre)\b", re.IGNORECASE),
    "absoluto": re.compile(
        r"\b(?:todos?\s+l[oa]s|todas\s+las|ning[uú]n[ao]?|nadie|nunca|siempre|jam[aá]s|"
        r"cero|por\s+primera\s+vez|ninguna\s+otra|el\s+[uú]nico|la\s+[uú]nica)\b", re.IGNORECASE),
    "causal": re.compile(
        r"\b(?:gracias\s+a|por\s+culpa\s+de|debido\s+a|a\s+causa\s+de|"
        r"como\s+consecuencia\s+de|se\s+debe\s+a)\b", re.IGNORECASE),
}

# Peso de cada marcador. Un porcentaje es más contrastable que un causal.
PESO_MARCADOR = {
    "porcentaje": 16, "cifra": 12, "magnitud": 10, "unidad_publica": 9,
    "ranking": 14, "comparacion": 8, "plazo": 7, "absoluto": 10, "causal": 5,
}

# ──────────────────────────────────────────────────────────────────────────────
# 4. Normalización
# ──────────────────────────────────────────────────────────────────────────────

_COMILLAS_APERTURA = "\"«“„‟‹"
_COMILLAS_CIERRE = "\"»”‟›"
RE_ENTRECOMILLADO = re.compile(
    r"[«“„‟]([^«»“”„‟]{12,400})[»”‟]"          # comillas tipográficas y latinas
    r"|\"([^\"]{12,400})\""                       # comillas rectas
)

RE_ESPACIOS = re.compile(r"\s+")
RE_FRASE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ«\"“¿¡])")

# Nombre propio de persona: al menos nombre y apellido, para no confundirlo con
# un topónimo suelto ("Canarias", "Tenerife") ni con el inicio de frase.
RE_NOMBRE = re.compile(
    r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}"
    r"(?:\s+(?:de|del|de\s+la|la|los|y)\s+)?"
    r"(?:\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}){1,3}"
)

# Falsos positivos frecuentes: entidades que casan con RE_NOMBRE pero no son
# personas. Se comparan normalizados.
NO_SON_PERSONAS = frozenset({
    "gobierno de canarias", "parlamento de canarias", "cabildo de tenerife",
    "cabildo de gran canaria", "gran canaria", "las palmas", "santa cruz",
    "santa cruz de tenerife", "las palmas de gran canaria", "puerto del rosario",
    "islas canarias", "union europea", "seguridad social", "coalicion canaria",
    "nueva canarias", "partido popular", "diputacion del comun", "canarias ahora",
    "servicio canario", "servicio canario de salud", "gobierno de espana",
    "consejo de ministros", "casa de gobierno", "cruz roja", "la laguna",
    "san cristobal", "san bartolome", "puerto de la cruz", "el hierro",
    "la gomera", "la palma", "la orotava", "los llanos", "santa lucia",
})


# Encabezados que abren titular con dos puntos sin ser un emisor: secciones,
# topónimos y etiquetas temáticas. "Canarias: las claves de la semana" no es
# una declaración de nadie.
NO_SON_EMISORES = frozenset({
    "canarias", "tenerife", "gran canaria", "lanzarote", "fuerteventura",
    "la palma", "la gomera", "el hierro", "la graciosa", "espana", "europa",
    "sucesos", "tribunales", "opinion", "politica", "sociedad", "economia",
    "deportes", "cultura", "sanidad", "educacion", "empleo", "vivienda",
    "turismo", "migracion", "justicia", "medio ambiente", "salud", "ciencia",
    "sucesion", "agenda", "entrevista", "analisis", "encuesta", "editorial",
    "elecciones", "presupuestos", "video", "directo", "en directo",
    "ultima hora", "en imagenes", "asi fue", "resumen", "claves", "el tiempo",
})


def _quitar_tildes(texto: str) -> str:
    nfkd = unicodedata.normalize("NFD", texto)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def normalizar(texto: str) -> str:
    """Minúsculas sin tildes, espacios colapsados. Para comparar, no para mostrar."""
    if not texto:
        return ""
    return RE_ESPACIOS.sub(" ", _quitar_tildes(texto.lower())).strip()


def limpiar(texto: str) -> str:
    """Deshace entidades HTML y colapsa espacios. Para mostrar.

    Cerca de una quinta parte del corpus llega con entidades sin decodificar
    (mismo problema documentado en `scripts/build_wordcloud_terms.py`). Sin este
    paso, las citas salen con `&oacute;` incrustado y los regex de comillas
    fallan contra `&quot;`.
    """
    if not texto:
        return ""
    return RE_ESPACIOS.sub(" ", html.unescape(texto)).strip()


# ──────────────────────────────────────────────────────────────────────────────
# 5. Modelo
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Actor:
    """Emisor de una declaración, tal como se le puede identificar en el texto."""
    texto: str                      # el sintagma tal cual aparece
    cargo: str = ""                 # etiqueta canónica del cargo
    cargo_completo: str = ""        # cargo + complemento
    area: str = ""                  # área de gestión ("sanidad", "empleo"…)
    ambito: str = ""                # autonomico | insular | municipal | estatal | partido
    institucion: str = ""           # institución explícita, si aparece
    nombre: str = ""                # nombre propio, si va en aposición
    ex_cargo: bool = False          # "el ex consejero": ya no ostenta el cargo

    @property
    def slug(self) -> str:
        base = self.nombre or self.cargo_completo or self.texto
        return re.sub(r"[^a-z0-9]+", "-", normalizar(base)).strip("-")[:120]


@dataclass
class Declaracion:
    """Una afirmación atribuida a un cargo, lista para revisión humana."""
    cita: str
    tipo_cita: str                  # titular | directa | indirecta | pospuesta
    actor: Actor
    verbo: str = ""
    verbo_lema: str = ""
    fuerza: str = "neutro"
    marcadores: list[str] = field(default_factory=list)
    temas: list[str] = field(default_factory=list)
    campo: str = "titulo"           # dónde se encontró
    contexto: str = ""
    prioridad: int = 0
    verificable: bool = False

    # Trazabilidad hacia la noticia de origen.
    medio: str = ""
    url: str = ""
    url_hash: str = ""
    fecha_pub: str | None = None

    @property
    def hash_declaracion(self) -> str:
        """Clave estable de deduplicación.

        Cuelga del `url_hash` de la noticia y del texto normalizado de la cita,
        no de la posición: así reprocesar el corpus no duplica filas ni pierde
        el estado de revisión que un humano ya haya asignado.
        """
        semilla = f"{self.url_hash}|{self.actor.slug}|{normalizar(self.cita)}"
        return hashlib.sha1(semilla.encode("utf-8")).hexdigest()

    def to_row(self) -> dict:
        """Fila lista para `medios.declaraciones`."""
        return {
            "hash_declaracion": self.hash_declaracion,
            "url_hash": self.url_hash,
            "url": self.url,
            "medio": self.medio,
            "fecha_pub": self.fecha_pub,
            "cita": self.cita,
            "tipo_cita": self.tipo_cita,
            "actor_texto": self.actor.texto,
            "actor_nombre": self.actor.nombre or None,
            "actor_slug": self.actor.slug,
            "cargo": self.actor.cargo or None,
            "cargo_completo": self.actor.cargo_completo or None,
            "area": self.actor.area or None,
            "ambito": self.actor.ambito or None,
            "institucion": self.actor.institucion or None,
            "ex_cargo": self.actor.ex_cargo,
            "verbo": self.verbo or None,
            "verbo_lema": self.verbo_lema or None,
            "fuerza": self.fuerza,
            "marcadores": self.marcadores,
            "temas": self.temas,
            "campo": self.campo,
            "contexto": self.contexto or None,
            "prioridad": self.prioridad,
            "verificable": self.verificable,
        }


# ──────────────────────────────────────────────────────────────────────────────
# 6. Identificación del actor
# ──────────────────────────────────────────────────────────────────────────────

def _expandir_complemento(texto: str, desde: int, max_tokens: int = 8) -> tuple[str, int]:
    """Extiende el cargo hacia la derecha sobre su complemento.

    `consejera` → `consejera de Sanidad del Gobierno de Canarias`.

    Avanza mientras encuentre conectores en minúscula o palabras capitalizadas,
    con un tope de tokens. El tope evita que un cargo al principio de frase se
    coma media oración cuando el complemento no está delimitado por comas.
    """
    resto = texto[desde:]
    tokens = re.findall(r"\S+", resto)
    tomados: list[str] = []
    consumido = 0
    espera_contenido = False

    for token in tokens[:max_tokens]:
        limpio = token.strip(",;:.")
        if not limpio:
            break
        norm = normalizar(limpio)
        es_conector = norm in _CONECTORES
        es_contenido = bool(re.match(r"^[A-ZÁÉÍÓÚÑ]", limpio)) or norm in AREAS_CARGO

        if es_conector:
            tomados.append(limpio)
            espera_contenido = True
        elif es_contenido:
            tomados.append(limpio)
            espera_contenido = False
        else:
            break

        # El complemento termina donde termina el sintagma: una coma o un punto
        # pegados al token cierran la expansión. La puntuación queda fuera del
        # tramo consumido para que el detector de aposiciones la siga viendo:
        # es justo la coma que separa el cargo del nombre.
        cierra = token[-1] in ",;:."
        consumido = resto.index(token, consumido) + len(token.rstrip(",;:."))
        if cierra:
            break

    # Un complemento no puede acabar en conector ("consejero de").
    while tomados and normalizar(tomados[-1]) in _CONECTORES:
        tomados.pop()
        espera_contenido = False

    if not tomados or espera_contenido:
        return "", 0
    return " ".join(tomados), consumido


def _clasificar_complemento(complemento: str) -> tuple[str, str, str]:
    """Devuelve (área temática, institución, ámbito) leídos del complemento."""
    norm = normalizar(complemento)

    institucion, ambito = "", ""
    for patron, canonica, amb in INSTITUCIONES:
        if patron in norm:
            institucion, ambito = canonica, amb
            break

    area = ""
    for etiqueta in sorted(AREAS_CARGO, key=len, reverse=True):
        if etiqueta in norm:
            area = etiqueta
            break

    return area, institucion, ambito


def _buscar_nombre_en_aposicion(texto: str, inicio_cargo: int, fin_cargo: int) -> str:
    """Busca el nombre propio en aposición al cargo.

    Cubre las dos disposiciones habituales en prensa:
        el presidente de Canarias, Fulano de Tal, aseguró…
        Fulano de Tal, presidente de Canarias, aseguró…

    Devolver el nombre desde el propio corpus evita mantener a mano un censo de
    cargos que cambia con cada remodelación de gobierno.
    """
    # Aposición pospuesta: cargo, NOMBRE,
    despues = texto[fin_cargo:fin_cargo + 90]
    m = re.match(r"\s*,\s*(" + RE_NOMBRE.pattern + r")\s*(?=[,.;:]|\s+(?:que|quien))", despues)
    if m:
        candidato = m.group(1).strip()
        if normalizar(candidato) not in NO_SON_PERSONAS:
            return candidato

    # Aposición antepuesta: NOMBRE, cargo
    antes = texto[max(0, inicio_cargo - 90):inicio_cargo]
    m = re.search(r"(" + RE_NOMBRE.pattern + r")\s*,\s*(?:el|la|los|las)?\s*$", antes)
    if m:
        candidato = m.group(1).strip()
        if normalizar(candidato) not in NO_SON_PERSONAS:
            return candidato

    return ""


def detectar_actores(texto: str) -> list[tuple[Actor, int, int]]:
    """Localiza los cargos del texto. Devuelve (actor, inicio, fin) por cada uno."""
    encontrados: list[tuple[Actor, int, int]] = []
    if not texto:
        return encontrados

    for m in RE_CARGO.finditer(texto):
        nucleo = m.group("nucleo")
        cargo_canonico, ambito_defecto = CARGOS_NUCLEO[normalizar(nucleo)]

        complemento, consumido = _expandir_complemento(texto, m.end())
        area, institucion, ambito = _clasificar_complemento(complemento)

        fin = m.end() + consumido
        cargo_completo = (nucleo + (" " + complemento if complemento else "")).strip()
        nombre = _buscar_nombre_en_aposicion(texto, m.start(), fin)

        # `area` conserva la etiqueta legible del complemento ("salud mental",
        # "bienestar social"). El tema del observatorio se deriva aparte, en
        # `tema_por_area()`, para no perder el nombre real de la consejería.
        actor = Actor(
            texto=texto[m.start("nucleo"):fin].strip().strip(" ,;:."),
            cargo=cargo_canonico,
            cargo_completo=cargo_completo,
            area=area,
            ambito=ambito or ambito_defecto,
            institucion=institucion,
            nombre=nombre,
            ex_cargo=bool(m.group("ex")),
        )
        encontrados.append((actor, m.start(), fin))

    return encontrados


def tema_por_area(area: str) -> str:
    """Traduce el área de un cargo al tema del observatorio, si hay equivalencia.

    No todas las áreas tienen tema: `AREAS_CARGO` incluye consejerías que el
    observatorio no sigue (Cultura, Deportes) precisamente para poder cerrar
    bien el complemento del cargo aunque después no enruten a ningún tema.
    """
    return AREAS_CARGO.get(normalizar(area), "")


# ──────────────────────────────────────────────────────────────────────────────
# 7. Detectores
# ──────────────────────────────────────────────────────────────────────────────
# Cuatro formas de atribuir habla en prensa. Cada detector devuelve candidatos
# en bruto; el enriquecimiento y la deduplicación son comunes y van después.

MIN_CITA = 20
MAX_CITA = 400
VENTANA_ATRIBUCION = 200     # caracteres a cada lado de una cita entrecomillada
VENTANA_ANTECEDENTE = 320    # alcance para recuperar un sujeto elidido
DISTANCIA_VERBO_ACTOR = 70   # separación máxima entre el verbo y su sujeto

RE_ATRIBUCION_POSPUESTA = re.compile(
    r",\s*(?:seg[uú]n|en\s+palabras\s+de|a\s+juicio\s+de|en\s+opini[oó]n\s+de|"
    r"tal\s+y\s+como\s+(?:afirm|asegur|se[ñn]al|explic|indic)\w*)\s+",
    re.IGNORECASE,
)


@dataclass
class _Candidato:
    cita: str
    tipo_cita: str
    actor: Actor
    verbo: str = ""
    verbo_lema: str = ""
    fuerza: str = "neutro"
    campo: str = "titulo"
    contexto: str = ""


def _frases(texto: str) -> Iterator[str]:
    for frase in RE_FRASE.split(texto):
        frase = frase.strip()
        if frase:
            yield frase


def _cita_valida(cita: str, exigir_verbo: bool = True) -> bool:
    """Descarta fragmentos demasiado cortos, demasiado largos o sin verbo.

    `exigir_verbo` sólo se activa donde el recorte es arbitrario: dentro de un
    entrecomillado o tras los dos puntos de un titular. En estilo indirecto la
    sintaxis ya garantiza que hay oración —`que` introduce una subordinada—, y
    exigir el verbo allí descartaría los subjuntivos, que son justo la forma
    que toman las citas tras un verbo de demanda o de valoración (`lamentó que
    la situación no mejore`).
    """
    cita = cita.strip()
    if not (MIN_CITA <= len(cita) <= MAX_CITA):
        return False
    if len(cita.split()) < 4:
        return False
    if not exigir_verbo:
        return True
    # Una declaración tiene verbo conjugado. Sin él suele ser un sintagma
    # nominal entrecomillado ("el 'efecto llamada'"), no una afirmación.
    #
    # La longitud vale como segunda vía porque el detector de formas finitas es
    # deliberadamente estrecho —deja fuera los presentes en `-a` y `-e`, que no
    # se distinguen de un sustantivo— y sin esta salida rechazaría aserciones
    # buenas como "esta ley perjudica a las familias". Los entrecomillados
    # nominales del corpus son cortos: "efecto llamada", "ruta canaria". A
    # partir de siete palabras dejan de serlo.
    #
    # El desequilibrio es intencionado. Colar una cita floja la deja al fondo de
    # una cola que revisa una persona; descartar una afirmación con datos la
    # pierde sin que nadie se entere.
    return _tiene_verbo_conjugado(cita) or len(cita.split()) >= 7


# Formas finitas de alta frecuencia. Cubren auxiliares, cópulas y los verbos con
# los que se enuncian datos públicos (subir, bajar, alcanzar, superar, invertir).
# Es una lista de cobertura, no un análisis morfológico: sirve para descartar
# sintagmas nominales, no para etiquetar la oración.
#
# Quedan fuera `está` y `esté`: al normalizar sin tildes colisionan con los
# demostrativos `esta` y `este`, que aparecen en casi cualquier fragmento. Como
# señal valdrían para todo, es decir, para nada; las cópulas las cubren `es`,
# `son`, `ha` y `han`.
_VERBOS_FINITOS = frozenset("""
es son era eran fue fueron sera seran seria serian estan estaba estaban
estara estaran hay ha han habia habian habra habran hemos tiene tienen tenia
tenian tendra tendran va van iba iban ira iran puede pueden podia podian podra
podran debe deben deberia deberian hace hacen hizo hicieron hara haran sube
suben subio baja bajan bajo crece crecen crecio cae caen cayo sigue siguen
existe existen queda quedan quedo supone suponen cuesta cuestan alcanza
alcanzan alcanzo supera superan supero llega llegan llego recibe reciben
recibio cobra cobran gasta gastan invierte invierten invirtio dedica dedican
cuenta cuentan dispone disponen necesita necesitan permite permiten garantiza
cumple cumplen funciona funcionan vive viven trabaja trabajan gana ganan
pierde pierden mejora mejoran empeora aumenta aumentan aumento disminuye
disminuyen reduce reducen redujo duplica triplica representa representan
asciende ascienden ronda rondan afecta afectan depende dependen falta faltan
sobra sobran cubre cubren atiende atienden espera esperan tarda tardan
sea sean esten haya hayan tenga tengan pueda puedan vaya vayan haga
hagan mejore mejoren empeore aumente suba baja llegue cumpla permita
garantice transfiera reciba dedique invierta cubra atienda exista quede
suponga apruebe abra cierre mantenga ponga saque quite deje
""".split())

# Sufijos que sólo aparecen en formas verbales. Se excluyen los ambiguos: `-ía`
# casaría con "día" o "policía", y `-ado` con "diputado" o "delegado".
_SUFIJOS_VERBALES = re.compile(
    r"[a-záéíóúñü]{2,}(?:ó|ará|erá|irá|arán|erán|irán|aron|ieron|"
    r"ando|endo|amos|emos|imos|remos)\b",
    re.IGNORECASE,
)


def _tiene_verbo_conjugado(cita: str) -> bool:
    """Comprueba que la cita contenga una forma verbal finita.

    Descarta los entrecomillados nominales, que en prensa canaria son
    abundantes (`el "efecto llamada"`, `la "ruta canaria"`) y llenarían la cola
    de matices tipográficos en vez de afirmaciones. No es un analizador
    morfológico: combina una lista de formas frecuentes con los sufijos que en
    castellano no comparten los sustantivos.
    """
    palabras = {normalizar(p) for p in re.findall(r"[\wáéíóúñüÁÉÍÓÚÑ]+", cita)}
    if palabras & _VERBOS_FINITOS:
        return True
    if any(normalizar(f) in FORMAS_VERBALES for f in palabras):
        return True
    return bool(_SUFIJOS_VERBALES.search(cita))


_BORDES_CITA = "".join(_COMILLAS_APERTURA + _COMILLAS_CIERRE) + " \t,;:.—–-"


def _limpiar_cita(cita: str) -> str:
    """Quita comillas y puntuación de los extremos.

    Se aplica en bucle porque los bordes se alternan: una cita indirecta que
    cierra una directa termina en `".` y una sola pasada dejaría el punto.
    """
    previo = None
    cita = cita.strip()
    while cita and cita != previo:
        previo = cita
        cita = cita.strip(_BORDES_CITA)
    return cita


def _actor_mas_cercano(
    actores: Sequence[tuple[Actor, int, int]], pos: int
) -> tuple[Actor, int] | None:
    """Actor cuyo sintagma queda más cerca de `pos`, con su distancia."""
    mejor: tuple[Actor, int] | None = None
    for actor, ini, fin in actores:
        distancia = 0 if ini <= pos <= fin else min(abs(pos - ini), abs(pos - fin))
        if mejor is None or distancia < mejor[1]:
            mejor = (actor, distancia)
    return mejor


def _atribucion_en_ventana(ventana: str) -> tuple[Actor, str, str, str] | None:
    """Busca en un fragmento la pareja verbo declarativo + cargo.

    Devuelve (actor, verbo, lema, fuerza). Se emparejan por proximidad: en
    `"…", aseguró la consejera de Sanidad`, el verbo y el sujeto van pegados,
    mientras que un cargo mencionado de pasada al otro extremo del párrafo no
    es quien habla.
    """
    actores = detectar_actores(ventana)
    if not actores:
        return None

    mejor: tuple[int, Actor, str, str, str] | None = None
    for m in RE_VERBO.finditer(ventana):
        lema, fuerza = FORMAS_VERBALES[normalizar(m.group("verbo"))]
        cercano = _actor_mas_cercano(actores, m.start())
        if cercano is None:
            continue
        actor, distancia = cercano
        if distancia > DISTANCIA_VERBO_ACTOR:
            continue
        if mejor is None or distancia < mejor[0]:
            mejor = (distancia, actor, m.group("verbo"), lema, fuerza)

    if mejor is None:
        return None
    _, actor, verbo, lema, fuerza = mejor
    return actor, verbo, lema, fuerza


def _recortar_tras_frase(ventana: str) -> str:
    """Corta la ventana en el primer final de frase.

    Sin este corte, `"…". El alcalde criticó la medida` atribuye la cita al
    alcalde, que sólo aparecía en la frase siguiente. Es el falso positivo más
    caro del detector: pone en boca de alguien algo que no dijo.
    """
    m = RE_FRASE.search(ventana)
    return ventana[:m.start()] if m else ventana


def _recortar_antes_de_frase(ventana: str) -> str:
    """Como `_recortar_tras_frase`, pero conservando la última frase."""
    limites = list(RE_FRASE.finditer(ventana))
    return ventana[limites[-1].end():] if limites else ventana


def detectar_titular(titulo: str) -> list[_Candidato]:
    """`Clavijo: "Canarias no puede asumir más llegadas"`.

    El titular con dos puntos es la forma más productiva del corpus y también
    la más limpia: el medio ya ha aislado la declaración y ha nombrado al
    emisor. Aquí el emisor puede venir sólo por apellido, así que no se exige
    el patrón completo de nombre y apellido.
    """
    titulo = limpiar(titulo)
    m = re.match(r"^(?P<emisor>[^:]{3,90}?)\s*:\s*(?P<cita>.{10,})$", titulo)
    if not m:
        return []

    emisor = m.group("emisor").strip()
    cita = _limpiar_cita(m.group("cita"))
    if not _cita_valida(cita):
        return []

    # Un emisor con verbo dentro no es un emisor, es una frase con dos puntos.
    if RE_VERBO.search(emisor) and not detectar_actores(emisor):
        return []

    entrecomillada = m.group("cita").lstrip()[:1] in _COMILLAS_APERTURA

    actores = detectar_actores(emisor)
    if actores:
        actor = actores[0][0]
    else:
        actor = _emisor_sin_cargo(emisor, entrecomillada)
        if actor is None:
            return []

    # El titular con dos puntos no lleva verbo introductorio, pero el medio ya
    # ha decidido que eso es lo que esa persona sostiene. Vale como aserción:
    # si no, ninguna cita de titular entraría nunca en la cola de verificación,
    # y es justo la forma en que más declaraciones contrastables se publican.
    return [_Candidato(cita=cita, tipo_cita="titular", actor=actor,
                       fuerza="asercion", campo="titulo", contexto=titulo)]


def _emisor_sin_cargo(emisor: str, entrecomillada: bool) -> Actor | None:
    """Interpreta el emisor de un titular cuando no declara cargo.

    `Torres: "…"` es una declaración; `Sanidad: "…"` o `Canarias: "…"` son
    encabezados de sección o de tema, no personas. Se rechaza lo que coincide
    con un área de gestión o con una entidad conocida, y sólo se rellena
    `nombre` cuando hay al menos un token con forma de antropónimo (mayúscula
    seguida de minúsculas). Así las siglas de partido siguen entrando como
    emisor, pero no se registran como si fueran el nombre de una persona.
    """
    norm = normalizar(emisor)
    if norm in AREAS_CARGO or norm in NO_SON_PERSONAS or norm in NO_SON_EMISORES:
        return None
    # Un apellido suelto sin comillas es indistinguible de una etiqueta de
    # sección, y la lista de etiquetas nunca estará completa. Con una sola
    # palabra se exigen comillas: el medio marca así que reproduce literalmente
    # lo dicho. Con nombre y apellido la ambigüedad desaparece y no hacen falta.
    if len(emisor.split()) == 1 and not entrecomillada:
        return None
    if not re.fullmatch(
        r"[A-ZÁÉÍÓÚÑ][\wáéíóúñüÁÉÍÓÚÑ.'-]*(?:\s+[A-ZÁÉÍÓÚÑ][\wáéíóúñüÁÉÍÓÚÑ.'-]*){0,3}",
        emisor,
    ):
        return None
    parece_persona = bool(re.search(r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]{2,}", emisor))
    return Actor(texto=emisor, nombre=emisor if parece_persona else "")


def detectar_citas_directas(texto: str, campo: str) -> list[_Candidato]:
    """`"…", aseguró la consejera` y `El presidente afirmó: "…"`."""
    candidatos: list[_Candidato] = []
    for m in RE_ENTRECOMILLADO.finditer(texto):
        cita = _limpiar_cita(m.group(1) or m.group(2) or "")
        if not _cita_valida(cita):
            continue

        # La prensa española pospone la atribución con mucha más frecuencia de
        # la que la antepone, así que la ventana posterior se mira primero.
        bruto_posterior = texto[m.end():m.end() + VENTANA_ATRIBUCION]
        bruto_anterior = texto[max(0, m.start() - VENTANA_ATRIBUCION):m.start()]
        posterior = _recortar_tras_frase(bruto_posterior)
        anterior = _recortar_antes_de_frase(bruto_anterior)

        atribucion = _atribucion_en_ventana(posterior) or _atribucion_en_ventana(anterior)
        if atribucion is None:
            atribucion = _atribucion_por_antecedente(texto, m.start(), posterior, anterior)
        if atribucion is None:
            continue

        actor, verbo, lema, fuerza = atribucion
        candidatos.append(
            _Candidato(
                cita=cita, tipo_cita="directa", actor=actor, verbo=verbo,
                verbo_lema=lema, fuerza=fuerza, campo=campo,
                contexto=limpiar(texto[max(0, m.start() - 120):m.end() + 120]),
            )
        )
    return candidatos


def _atribucion_por_antecedente(
    texto: str, inicio_cita: int, posterior: str, anterior: str
) -> tuple[Actor, str, str, str] | None:
    """Resuelve `"…", aseguró.`: verbo declarativo sin sujeto explícito.

    Es una elipsis habitual cuando el emisor ya se ha nombrado en la frase
    anterior. Se toma el último cargo mencionado antes de la cita, que es lo
    que hace también quien lee. El alcance se limita a `VENTANA_ANTECEDENTE`
    para no saltar a un cargo citado varios párrafos atrás.
    """
    verbo = RE_VERBO.search(posterior) or RE_VERBO.search(anterior)
    if verbo is None:
        return None
    previos = detectar_actores(texto[max(0, inicio_cita - VENTANA_ANTECEDENTE):inicio_cita])
    if not previos:
        return None
    lema, fuerza = FORMAS_VERBALES[normalizar(verbo.group("verbo"))]
    return previos[-1][0], verbo.group("verbo"), lema, fuerza


def detectar_estilo_indirecto(texto: str, campo: str) -> list[_Candidato]:
    """`La consejera de Sanidad aseguró que las listas de espera han bajado`."""
    candidatos: list[_Candidato] = []
    for frase in _frases(texto):
        actores = detectar_actores(frase)
        if not actores:
            continue

        for m in re.finditer(r"(?<![\wáéíóúñü])que\s+", frase, re.IGNORECASE):
            # El verbo declarativo tiene que estar justo antes del "que".
            previo = frase[max(0, m.start() - 40):m.start()]
            verbos = list(RE_VERBO.finditer(previo))
            if not verbos:
                continue
            v = verbos[-1]
            # Sólo si el verbo es lo último antes del "que": descarta
            # subordinadas donde el verbo quedó lejos ("aseguró el lunes, en
            # una comparecencia en la que…").
            if len(previo) - v.end() > 3:
                continue

            lema, fuerza = FORMAS_VERBALES[normalizar(v.group("verbo"))]
            pos_verbo = max(0, m.start() - 40) + v.start()
            cercano = _actor_mas_cercano(actores, pos_verbo)
            if cercano is None or cercano[1] > DISTANCIA_VERBO_ACTOR:
                continue

            cita = _limpiar_cita(frase[m.end():])
            if not _cita_valida(cita, exigir_verbo=False):
                continue

            candidatos.append(
                _Candidato(
                    cita=cita, tipo_cita="indirecta", actor=cercano[0],
                    verbo=v.group("verbo"), verbo_lema=lema, fuerza=fuerza,
                    campo=campo, contexto=limpiar(frase),
                )
            )
    return candidatos


def detectar_atribucion_pospuesta(texto: str, campo: str) -> list[_Candidato]:
    """`Las listas de espera han bajado un 12%, según la consejera de Sanidad`."""
    candidatos: list[_Candidato] = []
    for frase in _frases(texto):
        m = RE_ATRIBUCION_POSPUESTA.search(frase)
        if not m:
            continue
        actores = detectar_actores(frase[m.end():m.end() + 120])
        if not actores:
            continue
        cita = _limpiar_cita(frase[:m.start()])
        if not _cita_valida(cita, exigir_verbo=False):
            continue
        candidatos.append(
            _Candidato(
                cita=cita, tipo_cita="pospuesta", actor=actores[0][0],
                verbo="", verbo_lema="", fuerza="asercion",
                campo=campo, contexto=limpiar(frase),
            )
        )
    return candidatos


# ──────────────────────────────────────────────────────────────────────────────
# 8. Anclajes y prioridad
# ──────────────────────────────────────────────────────────────────────────────

def detectar_marcadores(cita: str) -> list[str]:
    """Tipos de anclaje verificable presentes en la cita."""
    return [nombre for nombre, patron in MARCADORES.items() if patron.search(cita)]


def calcular_prioridad(cand: _Candidato, marcadores: Sequence[str]) -> int:
    """Puntúa de 0 a 100 el interés de la declaración para verificación.

    Manda la fuerza asertiva, porque decide si hay algo que contrastar. Los
    anclajes suman por su contrastabilidad. Un nombre propio identificado sube
    la nota: sin nombre, la declaración es difícil de atribuir en una pieza
    publicada. Un ex cargo resta: lo que dijo sigue siendo noticiable, pero ya
    no compromete a la institución.
    """
    puntos = PESO_FUERZA.get(cand.fuerza, 10)
    puntos += min(40, sum(PESO_MARCADOR.get(m, 4) for m in marcadores))

    if cand.actor.nombre:
        puntos += 10
    if cand.actor.institucion:
        puntos += 4
    if cand.tipo_cita in ("titular", "directa"):
        puntos += 6      # literal: se puede citar sin reinterpretar al medio
    if cand.actor.ex_cargo:
        puntos -= 8

    return max(0, min(100, puntos))


def es_verificable(fuerza: str, marcadores: Sequence[str]) -> bool:
    """Una declaración entra en la cola si afirma algo contrastable.

    Las aserciones necesitan un anclaje: sin cifra, ranking, plazo ni absoluto,
    contrastarlas es una discusión, no una verificación. Los compromisos entran
    siempre: una promesa se puede seguir aunque no lleve número.
    """
    if fuerza not in FUERZAS_VERIFICABLES:
        return False
    if fuerza == "compromiso":
        return True
    return bool(marcadores)


# ──────────────────────────────────────────────────────────────────────────────
# 9. API pública
# ──────────────────────────────────────────────────────────────────────────────

def _temas_de(cand: _Candidato, temas_noticia: Sequence[str], clasificar_cita: bool) -> list[str]:
    """Temas de la declaración: los de la noticia, el área del cargo y, si se
    pide, los que el clasificador reconozca en la cita.

    El área del cargo aporta información que el titular a veces no lleva: si
    habla la consejera de Sanidad, la declaración es de sanidad aunque la cita
    no repita la palabra.
    """
    temas = list(dict.fromkeys(t for t in temas_noticia if t))

    tema_area = tema_por_area(cand.actor.area)
    if tema_area and tema_area not in temas:
        temas.append(tema_area)

    if clasificar_cita:
        try:
            from clasificador import clasificar
        except ImportError:
            return temas
        # La cita va en el campo de título porque el clasificador lo pondera
        # más: una declaración es corta y densa, como un titular.
        for tema in clasificar(cand.cita):
            if tema not in temas:
                temas.append(tema)

    return temas


def extraer_declaraciones(noticia: dict, clasificar_cita: bool = True) -> list[Declaracion]:
    """Extrae las declaraciones de una noticia.

    `noticia` usa las columnas de `medios.noticias`: titulo, resumen,
    texto_full, medio, url, url_hash, fecha_pub, temas.

    Devuelve una lista ordenada por prioridad descendente y deduplicada por
    `hash_declaracion`: una misma frase citada en el titular y repetida en el
    cuerpo es una sola declaración, y se conserva la versión mejor puntuada.
    """
    titulo = limpiar(str(noticia.get("titulo") or ""))
    resumen = limpiar(str(noticia.get("resumen") or ""))
    texto_full = limpiar(str(noticia.get("texto_full") or ""))
    temas_noticia = noticia.get("temas") or []
    if isinstance(temas_noticia, str):
        temas_noticia = [t.strip() for t in temas_noticia.strip("{}[]").split(",") if t.strip()]

    candidatos: list[_Candidato] = []
    candidatos += detectar_titular(titulo)
    for campo, texto in (("titulo", titulo), ("resumen", resumen), ("texto_full", texto_full)):
        if not texto:
            continue
        candidatos += detectar_citas_directas(texto, campo)
        candidatos += detectar_estilo_indirecto(texto, campo)
        candidatos += detectar_atribucion_pospuesta(texto, campo)

    por_hash: dict[str, Declaracion] = {}
    for cand in candidatos:
        marcadores = detectar_marcadores(cand.cita)
        decl = Declaracion(
            cita=cand.cita,
            tipo_cita=cand.tipo_cita,
            actor=cand.actor,
            verbo=cand.verbo,
            verbo_lema=cand.verbo_lema,
            fuerza=cand.fuerza,
            marcadores=marcadores,
            temas=_temas_de(cand, temas_noticia, clasificar_cita),
            campo=cand.campo,
            contexto=cand.contexto[:600],
            prioridad=calcular_prioridad(cand, marcadores),
            verificable=es_verificable(cand.fuerza, marcadores),
            medio=str(noticia.get("medio") or ""),
            url=str(noticia.get("url") or ""),
            url_hash=str(noticia.get("url_hash") or ""),
            fecha_pub=noticia.get("fecha_pub"),
        )
        previa = por_hash.get(decl.hash_declaracion)
        if previa is None or decl.prioridad > previa.prioridad:
            por_hash[decl.hash_declaracion] = decl

    return sorted(por_hash.values(), key=lambda d: d.prioridad, reverse=True)


def resumen_actor(declaraciones: Sequence[Declaracion]) -> list[dict]:
    """Agrega las declaraciones por actor.

    Es la materia prima del registro curado: en vez de mantener a mano un censo
    de cargos, ODESOCAN revisa esta agregación —quién aparece, con qué cargo y
    con qué frecuencia— y promueve a `medios.actores` lo que sea correcto.
    """
    por_slug: dict[str, dict] = {}
    for decl in declaraciones:
        clave = decl.actor.slug
        if not clave:
            continue
        entrada = por_slug.setdefault(clave, {
            "actor_slug": clave,
            "nombre": decl.actor.nombre or None,
            "cargos": set(),
            "ambitos": set(),
            "instituciones": set(),
            "medios": set(),
            "n_declaraciones": 0,
            "n_verificables": 0,
        })
        entrada["n_declaraciones"] += 1
        entrada["n_verificables"] += int(decl.verificable)
        if decl.actor.cargo_completo:
            entrada["cargos"].add(decl.actor.cargo_completo)
        if decl.actor.ambito:
            entrada["ambitos"].add(decl.actor.ambito)
        if decl.actor.institucion:
            entrada["instituciones"].add(decl.actor.institucion)
        if decl.medio:
            entrada["medios"].add(decl.medio)
        if not entrada["nombre"] and decl.actor.nombre:
            entrada["nombre"] = decl.actor.nombre

    salida = []
    for entrada in por_slug.values():
        salida.append({
            **{k: v for k, v in entrada.items() if not isinstance(v, set)},
            "cargos": sorted(entrada["cargos"]),
            "ambitos": sorted(entrada["ambitos"]),
            "instituciones": sorted(entrada["instituciones"]),
            "medios": sorted(entrada["medios"]),
        })
    return sorted(salida, key=lambda e: e["n_declaraciones"], reverse=True)
