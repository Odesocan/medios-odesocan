"""
Clientes HTTP.

Dos clases intercambiables por duck-typing (ambas exponen `.get(url)`):

    ClienteHTTP        httpx + caché en disco + reintentos + stale-if-error
    ClientePlaywright  Chromium headless, para portadas que renderizan con JS

Solo `canariasahora` necesita Playwright (marcado con `playwright: True` en
`config/medios.py`).

Las pausas de `_esperar()` son deliberadas: el scraper imita el ritmo de un
lector humano, con un 12% de probabilidad de una pausa larga.
"""

import logging
import random
import time
import urllib.robotparser
from typing import Optional
from urllib.parse import urlparse

import httpx

from observatorio.comun.texto import url_hash
from observatorio.config.rutas import CACHE_DIR
from observatorio.config.scraping import SCRAPER, USER_AGENTS

try:
    from playwright.sync_api import sync_playwright as _sync_playwright
    _PLAYWRIGHT_DISPONIBLE = True
except ImportError:
    _PLAYWRIGHT_DISPONIBLE = False

log = logging.getLogger("scraper")


def _codificaciones_soportadas() -> str:
    """
    Accept-Encoding construido con lo que REALMENTE se sabe descomprimir.

    Anunciar `br` sin tener instalado brotli es un fallo silencioso: httpx
    devuelve los bytes sin descomprimir, `r.text` da binario, el binario supera
    el control de longitud mínima y acaba cacheado como si fuera HTML. El medio
    afectado rinde cero sin que salte ningún error.
    """
    codecs = ["gzip", "deflate"]
    try:
        import brotli  # noqa: F401
        codecs.append("br")
    except ImportError:
        try:
            import brotlicffi  # noqa: F401
            codecs.append("br")
        except ImportError:
            pass
    return ", ".join(codecs)


_ACCEPT_ENCODING = _codificaciones_soportadas()


def _parece_markup(texto: str) -> bool:
    """¿La respuesta parece HTML/XML/JSON y no binario mal descomprimido?"""
    if not texto:
        return False
    cabeza = texto.lstrip()[:400].lower()
    if cabeza.startswith(("{", "[")):          # JSON (API de WordPress)
        return True
    if any(m in cabeza for m in ("<!doctype", "<html", "<?xml", "<rss", "<feed")):
        return True
    # Último recurso: densidad de caracteres imprimibles en la cabecera
    muestra = texto[:1000]
    imprimibles = sum(1 for c in muestra if c.isprintable() or c in "\n\r\t")
    return imprimibles / max(len(muestra), 1) > 0.9

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
            "Accept-Encoding": _ACCEPT_ENCODING,
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
        "Accept-Encoding": _ACCEPT_ENCODING,
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
                if html and len(html.strip()) > 200 and _parece_markup(html):
                    cache_file.write_text(html, encoding="utf-8")
                    return html
                elif html and not _parece_markup(html):
                    # No se cachea: cachear binario envenena la caché durante
                    # `cache_ttl_dias` y deja al medio a cero sin ningún error.
                    log.warning(
                        "Respuesta ilegible (¿compresión no soportada?) en %s — no se cachea", url)
                else:
                    log.warning("Respuesta sospechosamente corta (%d bytes) para %s",
                                len(html or ""), url)
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

    def get(self, url: str, wait_until: str = "networkidle", usar_cache: bool = True) -> Optional[str]:
        """Navega a `url` y devuelve el HTML completamente renderizado.

        `usar_cache` se acepta y se ignora: Playwright no cachea, pero la firma
        tiene que coincidir con la de ClienteHTTP porque ambos se usan
        indistintamente por duck-typing.
        """
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
