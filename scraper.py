"""
scraper.py — Recolector de noticias de medios canarios
Estrategia: RSS primero → HTML como fallback → caché para reproducibilidad

Uso:
    python scraper.py                     # Scraping completo de todos los medios
    python scraper.py --medio canarias7  # Solo un medio
    python scraper.py --dry-run          # Prueba sin guardar en BD
"""

import argparse
import hashlib
import json
import logging
import os
import random
import re
import sqlite3
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import feedparser
import httpx
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright as _sync_playwright
    _PLAYWRIGHT_DISPONIBLE = True
except ImportError:
    _PLAYWRIGHT_DISPONIBLE = False

from clasificador import CLASIFICADOR_VERSION, clasificar
from config import CACHE_DIR, DB_PATH, LOG_DIR, MEDIOS, SCRAPER, USER_AGENTS

log = logging.getLogger("scraper")


def configurar_logging() -> None:
    """Configura logging por defecto si la aplicación aún no lo hizo."""
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_DIR / f"scraper_{datetime.now():%Y%m%d}.log"),
        ],
    )


# ── Procedencia de la fecha de publicación (R4) ───────────────────────────────
# Sin saber de dónde sale `fecha_pub` no se distingue una fecha real de la hora
# del raspado, y cualquier análisis de precedencia se vuelve arqueología. Cada
# pieza guarda su procedencia en `noticias.fecha_pub_origen`.
ORIGEN_RSS = "rss"            # fecha del feed: hora exacta
ORIGEN_URL = "url"            # embebida en la ruta: precisión de DÍA
ORIGEN_JSONLD = "jsonld"      # datePublished del artículo: hora exacta
ORIGEN_META = "meta"          # etiqueta <meta> del artículo: hora exacta
ORIGEN_TIME = "time"          # etiqueta <time datetime>: hora exacta
ORIGEN_API = "api"            # API propia del medio: hora exacta
ORIGEN_SINTETICO = "sintetica"  # NO es fecha de publicación: es la del raspado

# Procedencias que permiten ordenar dentro de una misma jornada. `url` queda
# fuera a propósito: tiene precisión de día, así que sirve para una serie diaria
# pero no para decidir quién publicó antes esta mañana.
ORIGENES_HORA_EXACTA = frozenset({ORIGEN_RSS, ORIGEN_JSONLD, ORIGEN_META, ORIGEN_TIME, ORIGEN_API})


def _run_id() -> str:
    """
    Identificador de la tirada, compartido por todas las cabeceras de la misma
    ejecución. Es lo que agrupa las observaciones de un mismo momento.
    """
    run = os.getenv("GITHUB_RUN_ID")
    intento = os.getenv("GITHUB_RUN_ATTEMPT", "1")
    if run:
        return f"gha-{run}-{intento}"
    return f"local-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"


# ── Base de datos ─────────────────────────────────────────────────────────────

def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Crea la BD y las tablas si no existen. Devuelve conexión."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")   # escrituras concurrentes seguras
    conn.execute("PRAGMA foreign_keys=ON")

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS noticias (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            url         TEXT    NOT NULL UNIQUE,
            url_hash    TEXT    NOT NULL UNIQUE,
            medio       TEXT    NOT NULL,
            titulo      TEXT    NOT NULL,
            resumen     TEXT,
            texto_full  TEXT,
            fecha_pub   TEXT,
            fecha_scrap TEXT    NOT NULL,
            fuente      TEXT    NOT NULL,   -- 'rss' | 'html'
            raw_json    TEXT,               -- payload original del feed
            temas       TEXT                -- JSON array de temas clasificados
        );

        CREATE TABLE IF NOT EXISTS scraping_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            medio       TEXT    NOT NULL,
            inicio      TEXT    NOT NULL,
            fin         TEXT,
            total       INTEGER DEFAULT 0,
            nuevas      INTEGER DEFAULT 0,
            errores     INTEGER DEFAULT 0,
            status      TEXT    DEFAULT 'running'
        );

        -- Una fila por pieza vista en cada tirada (R2). Mide permanencia en
        -- portada y posición en el listado, no el alta: una pieza que lleva
        -- semanas en el corpus sigue generando observaciones mientras siga
        -- destacada.
        CREATE TABLE IF NOT EXISTS observaciones (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash     TEXT    NOT NULL,
            medio        TEXT    NOT NULL,
            run_id       TEXT    NOT NULL,
            observado_en TEXT    NOT NULL,
            posicion     INTEGER,
            fuente       TEXT    NOT NULL,
            UNIQUE (url_hash, run_id)
        );

        CREATE INDEX IF NOT EXISTS idx_medio      ON noticias(medio);
        CREATE INDEX IF NOT EXISTS idx_fecha_pub  ON noticias(fecha_pub);
        CREATE INDEX IF NOT EXISTS idx_url_hash   ON noticias(url_hash);
        CREATE INDEX IF NOT EXISTS idx_obs_hash   ON observaciones(url_hash);
        CREATE INDEX IF NOT EXISTS idx_obs_run    ON observaciones(run_id);
    """)
    # Migración: añadir columnas nuevas si la BD ya existía sin ellas
    for col, defn in [
        ("temas", "TEXT"),
        ("texto_full", "TEXT"),
        ("fecha_pub_origen", "TEXT"),
        ("clasificador_version", "TEXT"),
        ("seccion", "TEXT"),
    ]:
        try:
            conn.execute(f"ALTER TABLE noticias ADD COLUMN {col} {defn}")
            conn.commit()
            log.info("Columna '%s' añadida a noticias (migración)", col)
        except sqlite3.OperationalError:
            pass  # ya existe

    log.info("BD inicializada en %s", db_path)
    return conn


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().encode()).hexdigest()[:16]


def ya_existe(conn: sqlite3.Connection, url: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM noticias WHERE url_hash = ?", (url_hash(url),)
    ).fetchone()
    return row is not None


def guardar_noticia(conn: sqlite3.Connection, noticia: dict) -> bool:
    """
    Inserta noticia. Devuelve True si es nueva, False si ya existía.

    Las piezas sin tema NO se descartan (R1): se guardan con `temas` vacío,
    porque son el denominador de cualquier medida de saliencia. Quien no las
    quiera, que filtre en la consulta; la vista pública `v_noticias_medios` ya
    lo hace por el dashboard.
    """
    h = url_hash(noticia["url"])
    temas = noticia.get("temas")
    if temas is None:
        temas = clasificar(
            noticia.get("titulo", ""),
            noticia.get("resumen", ""),
            noticia.get("url", ""),
        )
    try:
        conn.execute(
            """INSERT INTO noticias
               (url, url_hash, medio, titulo, resumen, texto_full,
                fecha_pub, fecha_pub_origen, fecha_scrap, fuente, raw_json,
                temas, clasificador_version, seccion)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                noticia["url"], h, noticia["medio"],
                noticia["titulo"], noticia.get("resumen"),
                noticia.get("texto_full"), noticia.get("fecha_pub"),
                noticia.get("fecha_pub_origen", ORIGEN_SINTETICO),
                datetime.now(timezone.utc).isoformat(),
                noticia["fuente"],
                json.dumps(noticia.get("raw"), ensure_ascii=False),
                json.dumps(temas, ensure_ascii=False),
                CLASIFICADOR_VERSION,
                noticia.get("seccion"),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False   # duplicado, normal


def registrar_observacion(
    conn: sqlite3.Connection,
    url: str,
    medio: str,
    run_id: str,
    observado_en: str,
    posicion: Optional[int],
    fuente: str,
) -> bool:
    """
    Anota que esta pieza seguía en el listado en esta tirada (R2).

    Es lo que permite medir duración de la atención y prominencia. Se registra
    tanto para las piezas nuevas como para las que ya estaban en el corpus: una
    pieza que aguanta cuatro días en portada genera dieciséis observaciones y
    una sola fila en `noticias`.
    """
    try:
        conn.execute(
            """INSERT OR IGNORE INTO observaciones
               (url_hash, medio, run_id, observado_en, posicion, fuente)
               VALUES (?,?,?,?,?,?)""",
            (url_hash(url), medio, run_id, observado_en, posicion, fuente),
        )
        conn.commit()
        return True
    except sqlite3.Error as e:
        log.warning("No se pudo registrar la observación de %s: %s", url, e)
        return False


# ── Helpers de comportamiento humano ─────────────────────────────────────────

def _esperar(feed: bool = False) -> None:
    """
    Pausa aleatoria entre peticiones.
    - feed=True usa un rango más corto (feeds RSS, menos sospechoso pedir rápido).
    - Con probabilidad 'pausa_larga_prob' inserta una pausa larga adicional.
    """
    if feed:
        espera = random.uniform(0.8, 2.0)
    else:
        espera = random.uniform(SCRAPER["delay_min"], SCRAPER["delay_max"])
    time.sleep(espera)

    if not feed and random.random() < SCRAPER["pausa_larga_prob"]:
        pausa = random.uniform(*SCRAPER["pausa_larga_rango"])
        log.debug("Pausa larga de %.1fs (comportamiento humano)", pausa)
        time.sleep(pausa)


def _headers_navegador(ua: str, es_feed: bool = False) -> dict:
    """
    Genera headers HTTP realistas para el UA dado.
    - es_feed=True: headers apropiados para RSS/Atom (Accept XML, sin Sec-Fetch de navegación).
    - es_feed=False (default): headers de carga de página HTML completa.
    """
    if es_feed:
        # Para feeds RSS/Atom: Accept que prioriza XML y no envía cabeceras
        # de navegación que delatan que no es un navegador real (Sec-Fetch-*).
        return {
            "User-Agent": ua,
            "Accept": (
                "application/rss+xml, application/atom+xml, "
                "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7"
            ),
            "Accept-Language": random.choice([
                "es-ES,es;q=0.9",
                "es-ES,es;q=0.9,en;q=0.8",
            ]),
            # Sin "br": httpx solo descomprime brotli si la librería está
            # instalada, y no lo está. Anunciarlo devuelve binario sin
            # descomprimir, que pasa el control de longitud mínima y se cachea
            # como si fuera HTML. Una cabecera entera puede rendir cero por
            # esto sin ningún error visible.
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    es_firefox = "Firefox" in ua
    return {
        "User-Agent": ua,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            if es_firefox else
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": random.choice([
            "es-ES,es;q=0.9",
            "es-ES,es;q=0.9,en;q=0.8",
            "es;q=0.9,en-US;q=0.8,en;q=0.7",
        ]),
        # Sin "br": httpx solo descomprime brotli si la librería está
            # instalada, y no lo está. Anunciarlo devuelve binario sin
            # descomprimir, que pasa el control de longitud mínima y se cachea
            # como si fuera HTML. Una cabecera entera puede rendir cero por
            # esto sin ningún error visible.
            "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
    }


# ── Cliente HTTP con reintentos ───────────────────────────────────────────────

class ClienteHTTP:
    def __init__(self):
        # Sin headers fijos: se establecen por petición con UA rotativo
        self.client = httpx.Client(
            timeout=SCRAPER["timeout"],
            follow_redirects=True,
        )
        self._robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}

    def _ua(self) -> str:
        return random.choice(USER_AGENTS)

    def _robots(self, url: str) -> urllib.robotparser.RobotFileParser:
        """Descarga y cachea robots.txt por dominio."""
        dominio = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
        if dominio not in self._robots_cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(f"{dominio}/robots.txt")
            try:
                rp.read()
            except Exception:
                pass   # Si falla, asumimos permitido
            self._robots_cache[dominio] = rp
        return self._robots_cache[dominio]

    def puede_scrapear(self, url: str) -> bool:
        if not SCRAPER["respetar_robots"]:
            return True
        rp = self._robots(url)
        # Comprobamos contra el UA genérico; cualquier UA del pool es válido
        return rp.can_fetch("*", url)

    def get(self, url: str, usar_cache: bool = True, es_feed: bool = False) -> Optional[str]:
        """GET con caché de fichero, UA rotativo, reintentos exponenciales y stale-if-error."""
        cache_file = CACHE_DIR / f"{url_hash(url)}.html"

        # Servir desde caché si es reciente
        if usar_cache and cache_file.exists():
            age_dias = (time.time() - cache_file.stat().st_mtime) / 86400
            if age_dias < SCRAPER["cache_ttl_dias"]:
                log.debug("Cache hit: %s", url)
                return cache_file.read_text(encoding="utf-8", errors="replace")

        if not self.puede_scrapear(url):
            log.warning("robots.txt prohíbe: %s", url)
            return None

        for intento in range(1, SCRAPER["max_reintentos"] + 1):
            ua = self._ua()
            try:
                _esperar(feed=es_feed)
                r = self.client.get(url, headers=_headers_navegador(ua, es_feed=es_feed))
                r.raise_for_status()
                html = r.text
                # Validación básica: descartar respuestas vacías o demasiado cortas
                if html and len(html.strip()) > 200:
                    cache_file.write_text(html, encoding="utf-8")
                    return html
                else:
                    log.warning("Respuesta sospechosamente corta (%d bytes) para %s", len(html), url)
            except httpx.HTTPStatusError as e:
                log.warning(
                    "HTTP %s en %s (intento %d, UA: ...%s)",
                    e.response.status_code,
                    url,
                    intento,
                    ua[-30:],
                )
                if e.response.status_code < 500:
                    break   # 4xx: no reintentar, pero caer al stale-if-error
            except (httpx.RequestError, httpx.TimeoutException) as e:
                log.warning("Error red en %s (intento %d): %s", url, intento, e)

            if intento < SCRAPER["max_reintentos"]:
                espera = 2 ** intento + random.uniform(0, 1.5)
                log.info("Reintentando en %.1fs…", espera)
                time.sleep(espera)

        # ── Stale-if-error: servir caché expirada antes de rendirse ──────────
        if cache_file.exists():
            log.warning("Sirviendo caché expirada (stale-if-error) para %s", url)
            return cache_file.read_text(encoding="utf-8", errors="replace")

        log.error("Fallaron todos los intentos para %s", url)
        return None

    def close(self) -> None:
        self.client.close()


# ── Cliente Playwright (para páginas JS-renderizadas) ─────────────────────────

class ClientePlaywright:
    """
    Renderiza páginas con Chromium headless.
    Úsalo sólo para medios con `playwright: True` en config.py.
    Comparte el navegador entre peticiones; ciérralo con .close().
    """

    # Extensiones bloqueadas para acelerar la carga (no son necesarias para el DOM)
    _BLOCK_EXT = (
        "*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp", "*.svg",
        "*.ico", "*.woff", "*.woff2", "*.ttf", "*.eot",
        "*.mp4", "*.mp3", "*.avi", "*.mov",
    )

    def __init__(self):
        if not _PLAYWRIGHT_DISPONIBLE:
            raise RuntimeError(
                "playwright no está instalado. "
                "Ejecuta: pip install playwright && playwright install chromium"
            )
        self._pw = _sync_playwright().__enter__()
        self._browser = self._pw.chromium.launch(headless=True)

    def get(self, url: str, wait_until: str = "networkidle") -> Optional[str]:
        """Navega a `url` y devuelve el HTML completamente renderizado."""
        ctx = None
        try:
            ctx = self._browser.new_context(
                user_agent=random.choice(USER_AGENTS),
                locale="es-ES",
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            for pat in self._BLOCK_EXT:
                page.route(pat, lambda route, **_: route.abort())
            page.goto(url, wait_until=wait_until, timeout=30_000)
            return page.content()
        except Exception as e:
            log.warning("Playwright error en %s: %s", url, e)
            return None
        finally:
            if ctx:
                ctx.close()

    def close(self) -> None:
        try:
            self._browser.close()
            self._pw.__exit__(None, None, None)
        except Exception:
            pass


# ── Parsers ───────────────────────────────────────────────────────────────────

def _normalizar_fecha(entry) -> Optional[str]:
    """Extrae fecha ISO 8601 desde un entry de feedparser."""
    for campo in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, campo, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return None


# Fechas embebidas en la ruta de la URL. Es la vía más barata: no cuesta
# ninguna petición, así que funciona también para las piezas del denominador,
# que nunca se descargan. Precisión de día.
_PATRONES_FECHA_URL = (
    re.compile(r"(?<!\d)(\d{4})/(\d{2})/(\d{2})(?!\d)"),        # /2026/09/07/
    re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"),        # /2026-09-04/
    re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})\d{6}(?!\d)"),    # sello de 14 dígitos
)

# Algunas cabeceras escriben la fecha en palabras dentro del slug, no en
# cifras: RTVC publica /…-11-septiembre-2026/. Es la misma vía barata de R4 —no
# cuesta ninguna petición, así que sirve también para el denominador— y la misma
# precisión de día.
_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_PATRON_FECHA_PALABRAS = re.compile(
    r"[-/](\d{1,2})-(" + "|".join(_MESES) + r")-(\d{4})(?![0-9a-z])"
)

_META_FECHA = (
    ("property", "article:published_time"),
    ("property", "og:published_time"),
    ("property", "article:published"),
    ("itemprop", "datePublished"),
    ("name", "date"),
    ("name", "pubdate"),
    ("name", "publish-date"),
    ("name", "DC.date.issued"),
)


def _iso_o_none(valor: object) -> Optional[str]:
    """Normaliza una marca temporal ISO 8601 a UTC. Devuelve None si no lo es."""
    if not valor or not isinstance(valor, str):
        return None
    texto = valor.strip()
    if not texto:
        return None
    if texto.endswith("Z"):
        texto = texto[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if not (2000 <= dt.year <= datetime.now(timezone.utc).year + 1):
        return None
    return dt.astimezone(timezone.utc).isoformat()


def fecha_desde_url(url: str) -> Optional[str]:
    """
    Extrae la fecha embebida en la ruta de la URL. Precisión de día: devuelve
    las 00:00 UTC de esa jornada, y quien ordene dentro de un día debe excluir
    esta procedencia.
    """
    if not url:
        return None
    ruta = urlparse(url).path
    limite = datetime.now(timezone.utc).year + 1
    for patron in _PATRONES_FECHA_URL:
        m = patron.search(ruta)
        if not m:
            continue
        anio, mes, dia = (int(g) for g in m.groups())
        if not (2000 <= anio <= limite):
            continue
        try:
            return datetime(anio, mes, dia, tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue   # 2026/13/40 y demás: no era una fecha

    m = _PATRON_FECHA_PALABRAS.search(ruta.lower())
    if m:
        dia, mes_texto, anio = int(m.group(1)), m.group(2), int(m.group(3))
        if 2000 <= anio <= limite:
            try:
                return datetime(anio, _MESES[mes_texto], dia, tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    return None


def fecha_desde_html(html: str) -> tuple[Optional[str], Optional[str]]:
    """
    Busca la fecha de publicación en el artículo ya descargado, por orden de
    fiabilidad: JSON-LD → <meta> → <time datetime>. Devuelve (fecha, origen).

    Solo se puede usar cuando la pieza se descarga, así que no cubre a las
    piezas sin tema: esas se quedan con la fecha de la URL o con marca
    sintética, y así queda registrado.
    """
    if not html:
        return None, None
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.select("script[type='application/ld+json']"):
        raw = script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        blobs = data if isinstance(data, list) else [data]
        for blob in list(blobs):
            if isinstance(blob, dict) and isinstance(blob.get("@graph"), list):
                blobs = blobs + blob["@graph"]
        for blob in blobs:
            if not isinstance(blob, dict):
                continue
            for campo in ("datePublished", "dateCreated", "uploadDate"):
                fecha = _iso_o_none(blob.get(campo))
                if fecha:
                    return fecha, ORIGEN_JSONLD

    for atributo, valor in _META_FECHA:
        etiqueta = soup.find("meta", attrs={atributo: valor})
        if etiqueta:
            fecha = _iso_o_none(etiqueta.get("content"))
            if fecha:
                return fecha, ORIGEN_META

    for etiqueta in soup.find_all("time"):
        fecha = _iso_o_none(etiqueta.get("datetime"))
        if fecha:
            return fecha, ORIGEN_TIME

    return None, None


def _fecha_de_listado(url: str) -> tuple[str, str]:
    """
    Mejor fecha disponible sin descargar el artículo, con su procedencia.
    Cuando no hay ninguna, se declara sintética: es la hora del raspado, y
    llamarla fecha de publicación sería mentir en la columna.
    """
    fecha = fecha_desde_url(url)
    if fecha:
        return fecha, ORIGEN_URL
    return datetime.now(timezone.utc).isoformat(), ORIGEN_SINTETICO


# Segmentos de ruta que no son sección: fechas, números de pieza y envoltorios
# genéricos de CMS.
_NO_SECCION = {
    "amp", "articulo", "articulos", "art", "contenido", "es", "index",
    "movil", "news", "noticia", "post", "web", "www",
}


def seccion_desde_url(url: str) -> Optional[str]:
    """
    Sección propia del medio, deducida de la ruta de la URL sin gastar ninguna
    petición. Es la taxonomía nativa de la cabecera, y sirve para contrastar
    contra ella los 15 temas del clasificador.
    """
    if not url:
        return None
    segmentos = [seg.strip().lower() for seg in urlparse(url).path.split("/") if seg.strip()]
    if len(segmentos) < 2:
        return None   # solo el slug: la URL no expone sección
    for seg in segmentos[:-1]:
        if seg.isdigit() or seg in _NO_SECCION:
            continue
        if not re.fullmatch(r"[a-záéíóúüñ0-9][a-záéíóúüñ0-9\-_]{1,39}", seg):
            continue
        return seg.replace("_", "-")
    return None


def _limpiar_html(texto: str) -> str:
    """Elimina etiquetas HTML de un fragmento de texto."""
    if not texto:
        return ""
    soup = BeautifulSoup(texto, "html.parser")
    return soup.get_text(separator=" ", strip=True)


def _article_body_desde_jsonld(html: str) -> Optional[str]:
    """Intenta extraer articleBody desde bloques JSON-LD."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select("script[type='application/ld+json']"):
        raw = script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if not isinstance(blob, dict):
                continue
            article_body = blob.get("articleBody")
            if article_body and len(str(article_body).strip()) > 100:
                return str(article_body).strip()[:5000]
    return None


def parsear_rss(
    medio_id: str,
    feed_url: str,
    cliente: ClienteHTTP,
    tope: int = 0,
) -> list[dict]:
    """
    Parsea un feed RSS/Atom. Devuelve lista de noticias normalizadas.

    Estrategia de doble intento para maximizar disponibilidad:
      1. feedparser fetcha la URL directamente (UA de navegador, Accept XML,
         soporta ETag/Last-Modified — más compatible con algunos CDN/WAF).
      2. Si falla o devuelve 0 entradas, httpx como fallback con UA rotativo.

    El feed se recorre entero (R1): `tope` es un seguro contra feeds
    desbocados, no una cuota de muestreo.
    """
    if tope <= 0:
        tope = SCRAPER["tope_seguridad_listado"]

    log.info("  RSS: %s", feed_url)
    ua = random.choice(USER_AGENTS)

    # ── Intento 1: feedparser directo con cabeceras de navegador ─────────────
    # feedparser usa urllib internamente; al pasarle request_headers con un UA
    # real y Accept XML, evitamos que algunos WAF rechacen peticiones de bots.
    _esperar(feed=True)
    try:
        feed = feedparser.parse(
            feed_url,
            agent=ua,
            request_headers={
                "Accept": (
                    "application/rss+xml, application/atom+xml, "
                    "application/xml;q=0.9, text/xml;q=0.8, */*;q=0.7"
                ),
                "Accept-Language": "es-ES,es;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Cache-Control": "no-cache",
            },
        )
    except Exception as e:
        log.warning("  feedparser directo falló en %s: %s", feed_url, e)
        feed = None

    # ── Intento 2: httpx con UA rotativo (fallback) ───────────────────────
    if not feed or (feed.bozo and not feed.entries):
        log.info("  RSS fallback httpx: %s", feed_url)
        html = cliente.get(feed_url, usar_cache=False, es_feed=True)
        if not html:
            log.warning("  Feed inaccesible (httpx): %s", feed_url)
            return []
        feed = feedparser.parse(html)

    if feed.bozo and not feed.entries:
        log.warning("  Feed malformado o vacío: %s", feed_url)
        return []

    noticias = []
    for entry in feed.entries[:tope]:
        url = getattr(entry, "link", None)
        titulo = _limpiar_html(getattr(entry, "title", ""))
        if not url or not titulo:
            continue
        url = url.strip()

        resumen_raw = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or ""
        )
        # El feed da hora exacta cuando la trae; si no, se cae a la URL y, en
        # último término, a la marca sintética, siempre declarando cuál es (R4).
        fecha = _iso_o_none(_normalizar_fecha(entry))
        origen = ORIGEN_RSS
        if not fecha:
            fecha, origen = _fecha_de_listado(url)

        noticias.append({
            "medio": medio_id,
            "url": url,
            "titulo": titulo,
            "resumen": _limpiar_html(resumen_raw)[:800],
            "fecha_pub": fecha,
            "fecha_pub_origen": origen,
            "seccion": seccion_desde_url(url),
            "fuente": "rss",
            "raw": {
                "feed_url": feed_url,
                "feed_title": feed.feed.get("title", ""),
                "tags": [t.term for t in getattr(entry, "tags", [])],
            },
        })

    # La posición es el rango dentro de ESTE listado (R2): no es comparable
    # entre un feed y una portada, y por eso viaja junto a `fuente`.
    for posicion, noticia in enumerate(noticias, start=1):
        noticia["posicion"] = posicion

    log.info("  → %d entradas en %s", len(noticias), feed_url)
    return noticias


def _extraer_desde_jsonld_portada(html: str, medio_id: str, cfg: dict, tope: int) -> list[dict]:
    """
    Extrae noticias desde bloques JSON-LD (ItemList, NewsArticle) en la portada.
    Muchos CMS modernos incluyen datos estructurados incluso cuando los selectores
    CSS cambian — esto actúa como red de seguridad complementaria.
    """
    soup = BeautifulSoup(html, "html.parser")
    noticias: list[dict] = []
    vistos: set[str] = set()

    for script in soup.select("script[type='application/ld+json']"):
        raw = script.get_text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        blobs = data if isinstance(data, list) else [data]
        for blob in blobs:
            if not isinstance(blob, dict):
                continue

            # ItemList con ListItem elements
            if blob.get("@type") == "ItemList":
                for item in blob.get("itemListElement", []):
                    url = item.get("url", "").strip()
                    nombre = item.get("name", "").strip()
                    if url and nombre and url not in vistos and _es_titular(nombre):
                        if _url_html_permitida(url, cfg):
                            vistos.add(url)
                            fecha, origen = _fecha_de_listado(url)
                            noticias.append({
                                "medio": medio_id,
                                "url": url,
                                "titulo": nombre,
                                "resumen": "",
                                "fecha_pub": fecha,
                                "fecha_pub_origen": origen,
                                "seccion": seccion_desde_url(url),
                                "fuente": "html",
                                "raw": {"origen": "json-ld", "tipo": "ItemList"},
                            })

            # NewsArticle / Article individual
            elif blob.get("@type") in ("NewsArticle", "Article", "ReportageNewsArticle"):
                url = blob.get("url", blob.get("mainEntityOfPage", ""))
                if isinstance(url, dict):
                    url = url.get("@id", "")
                titulo = blob.get("headline", "").strip()
                if url and titulo and url not in vistos and _es_titular(titulo):
                    if _url_html_permitida(url, cfg):
                        vistos.add(url)
                        # El JSON-LD de portada suele traer datePublished: es
                        # hora exacta y gratis, mejor que la ruta de la URL.
                        fecha = _iso_o_none(blob.get("datePublished"))
                        origen = ORIGEN_JSONLD if fecha else None
                        if not fecha:
                            fecha, origen = _fecha_de_listado(url)
                        noticias.append({
                            "medio": medio_id,
                            "url": url,
                            "titulo": titulo,
                            "resumen": (blob.get("description") or "")[:800],
                            "fecha_pub": fecha,
                            "fecha_pub_origen": origen,
                            "seccion": seccion_desde_url(url),
                            "fuente": "html",
                            "raw": {"origen": "json-ld", "tipo": blob.get("@type")},
                        })

            if len(noticias) >= tope:
                break

    return noticias[:tope]


# Por debajo de esto, una portada se considera mal cosechada y se complementa
# con JSON-LD. Sustituye al viejo criterio "menos de media cuota", que dejó de
# tener sentido al quitar la cuota.
_COSECHA_MINIMA_PORTADA = 12


def _es_titular(titulo: str) -> bool:
    """
    Distingue un titular de un enlace de navegación.

    Por el mismo selector CSS que las piezas entran «Ver más», «Sucesos» o
    «Última hora», que son enlaces a secciones, no noticias. Antes daba igual:
    no pasaban el filtro temático y desaparecían. Desde R1 nada desaparece, así
    que contarían como denominador e inflarían el total de lo que la cabecera
    destacó, deflactando todas las cuotas de saliencia.

    El criterio es estructural, no una lista de palabras: un titular de prensa
    tiene cuerpo. En la primera tirada real sobre El Hierro Hoy esto separaba
    seis enlaces de navegación de treinta y siete titulares.
    """
    limpio = " ".join((titulo or "").split())
    return len(limpio) >= 20 and len(limpio.split()) >= 3


def parsear_html_portada(
    medio_id: str,
    cfg: dict,
    cliente,          # ClienteHTTP o ClientePlaywright (duck-typing: ambos tienen .get(url))
    tope: int = 0,
) -> list[dict]:
    """
    Extrae titulares de la portada HTML como fallback o complemento al RSS.
    Usa los selectores CSS definidos en config.py.
    Acepta tanto ClienteHTTP (httpx) como ClientePlaywright (Chromium headless).

    Estrategia de doble extracción:
      1. Selectores CSS (fuente principal, configurable por medio)
      2. JSON-LD / datos estructurados (red de seguridad ante cambios de template)
    """
    if not cfg.get("selectores"):
        return []
    if tope <= 0:
        tope = SCRAPER["tope_seguridad_listado"]

    motor = "Playwright" if isinstance(cliente, ClientePlaywright) else "HTML"
    log.info("  %s: %s", motor, cfg["url"])
    # El listado NUNCA se sirve de caché: una portada de hace seis días
    # fabricaría permanencia falsa en la tabla de observaciones (R2). El caché
    # sigue valiendo para los artículos, que no cambian.
    if isinstance(cliente, ClienteHTTP):
        html = cliente.get(cfg["url"], usar_cache=False)
    else:
        html = cliente.get(cfg["url"])
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    sel_titular = cfg["selectores"].get("titular", "h2 a")
    sel_resumen = cfg["selectores"].get("resumen", "")

    vistos: set[str] = set()
    noticias: list[dict] = []

    navegacion = 0
    for enlace in soup.select(sel_titular):
        titulo = enlace.get_text(strip=True)
        href = enlace.get("href", "").strip()
        if not titulo or not href:
            continue
        if href.startswith(("#", "javascript:", "mailto:")):
            continue
        if not _es_titular(titulo):
            navegacion += 1
            continue

        url = urljoin(cfg["url"], href)
        if not _url_html_permitida(url, cfg):
            continue
        if url in vistos:
            continue
        vistos.add(url)

        # Intentar obtener resumen del nodo adyacente
        resumen = ""
        if sel_resumen:
            parent = enlace.find_parent(["article", "div", "li", "section"])
            if parent:
                nodo_res = parent.select_one(sel_resumen)
                if nodo_res:
                    resumen = nodo_res.get_text(strip=True)[:800]

        fecha, origen = _fecha_de_listado(url)
        noticias.append({
            "medio": medio_id,
            "url": url,
            "titulo": titulo,
            "resumen": resumen,
            "fecha_pub": fecha,
            "fecha_pub_origen": origen,
            "seccion": seccion_desde_url(url),
            "fuente": "html",
            "raw": {"origen": "portada", "selector": sel_titular},
        })
        if len(noticias) >= tope:
            break

    # ── Fallback JSON-LD: red de seguridad ante cambios de plantilla ─────────
    # Antes se disparaba al bajar de media cuota; sin cuota, el criterio es una
    # cosecha anormalmente pobre para una portada.
    if len(noticias) < _COSECHA_MINIMA_PORTADA:
        log.info("  JSON-LD fallback (selectores CSS dieron solo %d)", len(noticias))
        jsonld_noticias = _extraer_desde_jsonld_portada(html, medio_id, cfg, tope)
        for n in jsonld_noticias:
            if n["url"] not in vistos:
                vistos.add(n["url"])
                noticias.append(n)
                if len(noticias) >= tope:
                    break

    for posicion, noticia in enumerate(noticias, start=1):
        noticia["posicion"] = posicion

    if navegacion:
        log.info("  (%d enlaces de navegación descartados)", navegacion)
    log.info("  → %d titulares %s en %s", len(noticias), motor, cfg["url"])
    return noticias


def _url_html_permitida(url: str, cfg: dict) -> bool:
    """Aplica filtros opcionales para aceptar solo URLs de artículo útiles."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False

    url_norm = url.lower()
    for patron in cfg.get("html_url_excludes", []):
        if patron.lower() in url_norm:
            return False

    regex = cfg.get("html_url_regex")
    if regex and not re.search(regex, url):
        return False

    return True


def texto_desde_html(html: str, url: str) -> Optional[str]:
    """
    Extrae el texto principal de un artículo ya descargado.
    Usa newspaper3k si está disponible, si no, heurística con BeautifulSoup.

    Se separa de la descarga porque del mismo HTML salen dos cosas: el cuerpo
    y la fecha de publicación (R4). Bajarlo dos veces sería pagar dos veces.
    """
    if not html:
        return None

    # Muchos medios exponen el cuerpo completo en JSON-LD aunque newspaper falle.
    texto_jsonld = _article_body_desde_jsonld(html)
    if texto_jsonld:
        return texto_jsonld

    # Intentar con newspaper3k (mejor extracción)
    try:
        from newspaper import Article

        art = Article(url, language="es")
        art.set_html(html)
        art.parse()
        if art.text and len(art.text) > 100:
            return art.text[:5000]
    except ImportError:
        pass
    except Exception as e:
        log.debug("newspaper3k falló en %s: %s", url, e)

    # Fallback: heurística con BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for selector in [
        "article", "[class*='article-body']", "[class*='entry-content']",
        "[class*='news-body']", "main", ".content",
    ]:
        nodo = soup.select_one(selector)
        if nodo:
            parrafos = [
                p.get_text(strip=True)
                for p in nodo.find_all("p")
                if len(p.get_text()) > 40
            ]
            texto = " ".join(parrafos)
            if len(texto) > 100:
                return texto[:5000]

    return None


def extraer_texto_articulo(url: str, cliente: ClienteHTTP) -> Optional[str]:
    """Descarga el artículo y devuelve su texto. Envoltorio de compatibilidad."""
    html = cliente.get(url)
    return texto_desde_html(html, url) if html else None


# ── Orquestador principal ─────────────────────────────────────────────────────

def scrapear_medio(
    medio_id: str,
    conn: sqlite3.Connection,
    cliente: ClienteHTTP,
    dry_run: bool = False,
    extraer_articulos: bool = False,
    run_id: Optional[str] = None,
    conocidos: Optional[set[str]] = None,
) -> dict:
    """
    Scraping completo de un medio: RSS → HTML → (opcional) texto completo.
    Devuelve estadísticas del proceso.

    Dos cosas distintas ocurren con cada pieza del listado:
      - se registra SIEMPRE una observación (R2), esté o no en el corpus: es lo
        que mide permanencia en portada y prominencia;
      - se da de alta en `noticias` solo si es nueva, con tema o sin él (R1).
    """
    cfg = MEDIOS.get(medio_id)
    if not cfg:
        raise ValueError(f"Medio '{medio_id}' no encontrado en config.py")

    log.info("━━ Scraping: %s ━━", cfg["nombre"])
    inicio = datetime.now(timezone.utc).isoformat()
    run_id = run_id or _run_id()
    conocidos = conocidos if conocidos is not None else set()
    stats = {
        "medio": medio_id,
        "total": 0,
        "nuevas": 0,
        "errores": 0,
        "observadas": 0,
        "sin_tema": 0,
        "textos": 0,
    }
    status = "ok"

    # Registrar inicio en log de BD. Ojo con el nombre: `log_id` es la fila de
    # scraping_log, y `run_id` identifica la tirada completa. Son cosas
    # distintas y confundirlas rompe el agrupamiento de las observaciones.
    log_id = None
    if not dry_run:
        cur = conn.execute(
            "INSERT INTO scraping_log (medio, inicio) VALUES (?,?)",
            (medio_id, inicio),
        )
        conn.commit()
        log_id = cur.lastrowid

    # Sin cuota de listado (R1): la portada se recorre entera y el tope es solo
    # un seguro. Lo que sí tiene presupuesto es el texto completo, que es la
    # parte cara y solo afecta al encuadre, no a la saliencia.
    tope = SCRAPER["tope_seguridad_listado"]
    presupuesto_texto = SCRAPER["texto_full_por_tirada"] if extraer_articulos else 0

    # Cliente HTML: httpx por defecto; Playwright para medios JS-renderizados
    cliente_html: ClienteHTTP | ClientePlaywright = cliente
    cliente_pw: Optional[ClientePlaywright] = None
    if cfg.get("playwright"):
        if not _PLAYWRIGHT_DISPONIBLE:
            log.warning(
                "Playwright no disponible para %s — usando httpx como fallback. "
                "Instala con: pip install playwright && playwright install chromium",
                medio_id,
            )
        else:
            cliente_pw = ClientePlaywright()
            cliente_html = cliente_pw

    try:
        # Recolectar noticias
        noticias: list[dict] = []

        if cfg["tipo"] in ("rss_only", "rss+html"):
            for feed_url in cfg.get("rss", []):
                try:
                    noticias += parsear_rss(medio_id, feed_url, cliente, tope=tope)
                except Exception as e:
                    log.error("Error RSS %s: %s", feed_url, e)
                    stats["errores"] += 1

        if cfg["tipo"] in ("html_only", "rss+html"):
            try:
                noticias += parsear_html_portada(medio_id, cfg, cliente_html, tope=tope)
            except Exception as e:
                log.error("Error HTML %s: %s", cfg["url"], e)
                stats["errores"] += 1

        # Deduplicar por URL dentro de esta ejecución. La primera aparición gana,
        # y con ella su posición y su listado de origen.
        vistas = set()
        noticias_unicas = []
        for n in noticias:
            if n["url"] not in vistas:
                vistas.add(n["url"])
                noticias_unicas.append(n)
        noticias_unicas = noticias_unicas[:tope]

        stats["total"] = len(noticias_unicas)
        log.info("  Total noticias únicas: %d", stats["total"])
        if stats["total"] >= tope:
            log.warning(
                "  %s alcanzó el tope de seguridad (%d): revisar el selector",
                medio_id, tope,
            )

        observado_en = datetime.now(timezone.utc).isoformat()

        for n in noticias_unicas:
            if dry_run:
                print(f"  [DRY-RUN] {n['medio']} | {n['titulo'][:70]}")
                stats["nuevas"] += 1
                continue

            # 1. La observación se registra siempre (R2)
            if registrar_observacion(
                conn, n["url"], medio_id, run_id, observado_en,
                n.get("posicion"), n["fuente"],
            ):
                stats["observadas"] += 1

            # 2. El alta, solo si la pieza es nueva. La consulta al corpus
            #    remoto evita que en integración continua, donde la base local
            #    arranca vacía, cada tirada vuelva a descargar lo ya conocido.
            if url_hash(n["url"]) in conocidos or ya_existe(conn, n["url"]):
                continue

            # 3. Clasificar. Sin tema NO es descarte (R1): es el denominador.
            temas = clasificar(
                n.get("titulo", ""),
                n.get("resumen", ""),
                n.get("url", ""),
            )
            n["temas"] = temas

            # 4. El cuerpo del artículo solo para piezas con tema y mientras
            #    quede presupuesto. Del mismo HTML sale la fecha real (R4).
            if temas and presupuesto_texto > 0:
                presupuesto_texto -= 1   # la petición se paga aunque falle
                html_articulo = cliente.get(n["url"])
                if html_articulo:
                    texto = texto_desde_html(html_articulo, n["url"])
                    if texto:
                        n["texto_full"] = texto
                        stats["textos"] += 1
                    if n.get("fecha_pub_origen") not in ORIGENES_HORA_EXACTA:
                        fecha, origen = fecha_desde_html(html_articulo)
                        if fecha:
                            n["fecha_pub"] = fecha
                            n["fecha_pub_origen"] = origen

            if guardar_noticia(conn, n):
                stats["nuevas"] += 1
                if not temas:
                    stats["sin_tema"] += 1
                log.info(
                    "  ✓ Nueva%s: %s",
                    "" if temas else " (sin tema, denominador)",
                    n["titulo"][:60],
                )
    except Exception:
        status = "error"
        raise
    finally:
        if not dry_run and log_id:
            try:
                conn.execute(
                    """UPDATE scraping_log
                       SET fin=?, total=?, nuevas=?, errores=?, status=?
                       WHERE id=?""",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        stats["total"],
                        stats["nuevas"],
                        stats["errores"],
                        status,
                        log_id,
                    ),
                )
                conn.commit()
            except Exception:
                log.exception("No se pudo cerrar scraping_log para %s", medio_id)
        if cliente_pw:
            cliente_pw.close()

    log.info(
        "  Resultado: %d nuevas (%d sin tema) / %d observadas / %d textos / "
        "%d en listado / %d errores",
        stats["nuevas"],
        stats["sin_tema"],
        stats["observadas"],
        stats["textos"],
        stats["total"],
        stats["errores"],
    )
    return stats


def hashes_conocidos() -> set[str]:
    """
    Pide al corpus remoto qué piezas ya están registradas.

    Con cuatro tiradas diarias esto es lo que evita multiplicar por cuatro el
    coste: en integración continua la base local arranca vacía en cada
    ejecución, así que sin esta consulta el scraper volvería a descargar el
    artículo de cada pieza ya conocida. Si no hay credenciales, se sigue sin
    ella: se pagan descargas de más, pero nada se rompe.
    """
    try:
        from supabase_loader import hashes_remotos

        conocidos = hashes_remotos()
        log.info("Corpus remoto: %d piezas ya conocidas", len(conocidos))
        return conocidos
    except Exception as e:
        log.warning(
            "No se pudo consultar el corpus remoto (%s). Se continúa sin él: "
            "puede haber descargas repetidas.", e,
        )
        return set()


def scrapear_todos(
    dry_run: bool = False,
    extraer_articulos: bool = False,
    medios: Optional[list[str]] = None,
) -> list[dict]:
    """Ejecuta el scraping para todos los medios (o los indicados)."""
    configurar_logging()
    conn = init_db()
    cliente = ClienteHTTP()
    medios_a_scrapear = medios or list(MEDIOS.keys())
    resultados = []
    inicio_total = time.time()

    # Un solo identificador para toda la tirada: es lo que agrupa las
    # observaciones de las distintas cabeceras en el mismo momento (R2).
    run_id = _run_id()
    conocidos = set() if dry_run else hashes_conocidos()

    log.info("Iniciando scraping de %d medios (tirada %s)", len(medios_a_scrapear), run_id)
    try:
        for medio_id in medios_a_scrapear:
            if medio_id not in MEDIOS:
                log.warning("Medio desconocido: %s (ignorado)", medio_id)
                continue
            try:
                stats = scrapear_medio(
                    medio_id,
                    conn,
                    cliente,
                    dry_run=dry_run,
                    extraer_articulos=extraer_articulos,
                    run_id=run_id,
                    conocidos=conocidos,
                )
                resultados.append(stats)
            except Exception as e:
                log.error("Error fatal en medio %s: %s", medio_id, e, exc_info=True)
                resultados.append({"medio": medio_id, "error": str(e)})
    finally:
        cliente.close()
        conn.close()

    elapsed = time.time() - inicio_total
    total_nuevas = sum(r.get("nuevas", 0) for r in resultados)
    total_obs = sum(r.get("observadas", 0) for r in resultados)
    total_sin_tema = sum(r.get("sin_tema", 0) for r in resultados)
    log.info(
        "━━ Scraping completado en %.1fs — %d nuevas (%d sin tema) / "
        "%d observaciones ━━",
        elapsed, total_nuevas, total_sin_tema, total_obs,
    )

    return resultados


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    configurar_logging()
    parser = argparse.ArgumentParser(
        description="Scraper de medios canarios"
    )
    parser.add_argument(
        "--medio", "-m",
        help="ID del medio a scrapear (por defecto: todos)",
        choices=list(MEDIOS.keys()),
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Prueba sin guardar en BD",
    )
    parser.add_argument(
        "--articulos", action="store_true",
        help="Extrae texto completo de cada noticia (más lento)",
    )
    parser.add_argument(
        "--lista-medios", action="store_true",
        help="Muestra los medios configurados y sale",
    )
    args = parser.parse_args()

    if args.lista_medios:
        print("\nMedios configurados:")
        for k, v in MEDIOS.items():
            feeds = len(v.get("rss", []))
            print(f"  {k:20s} — {v['nombre']} ({feeds} feeds RSS, tipo: {v['tipo']})")
        raise SystemExit(0)

    medios = [args.medio] if args.medio else None
    scrapear_todos(
        dry_run=args.dry_run,
        extraer_articulos=args.articulos,
        medios=medios,
    )
