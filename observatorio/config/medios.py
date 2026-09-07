"""
Medios canarios que se observan.

Añadir una cabecera es añadir una entrada a este diccionario; no hay que tocar
nada más del pipeline. Recuerda replicar la clave en `LM` y `MEDIO_COLORS` de
`index.html` para que el dashboard la muestre con nombre y color propios.
"""
# ── Medios canarios ───────────────────────────────────────────────────────────
# Cada medio tiene:
#   rss   → lista de feeds RSS/Atom (vacía si no tiene)
#   url   → portada para scraping HTML directo
#   color → para el dashboard
#   tipo  → "rss_only" | "html_only" | "rss+html"
#   selectores → CSS selectors para extraer titulares del HTML (si aplica)
#   html_url_regex / html_url_excludes → filtros opcionales sobre URLs HTML

MEDIOS = {
    "canarias7": {
        "nombre":  "Canarias7",
        "color":   "#1a5fa8",
        "url":     "https://www.canarias7.es",
        "rss": [
            "https://www.canarias7.es/rss/2.0/",
        ],
        "tipo": "rss+html",
        # Cuota moderada: RSS trae ~50 items; aumentada de 20→30 para capturar
        # más artículos regionales que rotan rápido en portada
        "max_items": 30,
        "selectores": {
            "titular": "h2.article-title a, h3.article-title a, article h2 a, h2 a, h3 a",
            "resumen": "p.article-summary, div.article-body p:first-of-type",
        },
    },
    "laprovincia": {
        "nombre":  "La Provincia",
        "color":   "#d63b2f",
        "url":     "https://www.laprovincia.es",
        "rss": [],
        "tipo": "html_only",   # RSS devuelve 404
        "max_items": 30,
        # Plataforma CDS Prensa Ibérica: h6 también usado en modNews
        "selectores": {
            "titular": "h2 a, h3 a, h6 a",
            "resumen": ".ft-mol-subtitle, p",
        },
        # Solo URLs con patrón /seccion/YYYY/MM/DD/slug-XXXXXXXX.html
        "html_url_regex": r"https://www\.laprovincia\.es/[\w/-]+/\d{4}/\d{2}/\d{2}/[\w-]+-\d+\.html",
    },
    "eldia": {
        "nombre":  "El Día",
        "color":   "#2e7d32",
        "url":     "https://www.eldia.es",
        "rss": [],
        "tipo": "html_only",   # RSS devuelve 404
        "max_items": 30,
        # Misma plataforma CDS Prensa Ibérica — URL regex filtra navegación y ticker
        "selectores": {
            "titular": "h2 a, h3 a",
            "resumen": ".ft-mol-subtitle, p",
        },
        "html_url_regex": r"https://www\.eldia\.es/[\w/-]+/\d{4}/\d{2}/\d{2}/[\w-]+-\d+\.html",
    },
    "diariodeavisos": {
        "nombre":  "Diario de Avisos",
        "color":   "#6a1b9a",
        "url":     "https://diariodeavisos.elespanol.com",
        "rss": [
            "https://diariodeavisos.elespanol.com/feed/",
        ],
        "tipo": "rss+html",
        "max_items": 30,
        # WordPress + Kadence Blocks (abril 2026): el tema cambió de Astra a Kadence.
        # Se añaden selectores para wp-block-kadence-advancedheading y kt-adv-heading,
        # manteniendo los anteriores como fallback por si la plantilla varía entre secciones.
        "selectores": {
            "titular": (
                "h2.entry-title a, .entry-title a, "
                ".wp-block-kadence-advancedheading a, .kt-adv-heading a, "
                "h2 a, h3 a"
            ),
            "resumen": ".entry-extracto, .entry-excerpt, .entry-summary, p",
        },
    },
    "laopinion": {
        "nombre":  "La Opinión de Tenerife",
        "color":   "#e65100",
        "url":     "https://www.laopinion.es",
        "rss": [],
        "tipo": "html_only",   # RSS redirige a epe.es (grupo editorial, no el medio)
        "max_items": 25,
        "selectores": {
            "titular": "h2 a, h3 a, .article-title a",
            "resumen": ".article-summary, p.subtitle",
        },
    },
    "elpueblocanario": {
        "nombre":  "El Pueblo Canario",
        "color":   "#00838f",
        "url":     "https://www.elpueblocanario.es",
        "rss": [],
        "tipo": "html_only",   # robots.txt bloquea el feed RSS
        "max_items": 25,
        "selectores": {
            "titular": "h2 a, h3 a, .entry-title a, article a",
            "resumen": ".entry-excerpt, .entry-summary, p.lead",
        },
        # AVISO (abril 2026): el sitio devuelve ECONNREFUSED de forma persistente.
        # Se mantiene en config para reactivar cuando el servidor vuelva online.
        # Total histórico scraping_log: 0 noticias desde el inicio del proyecto.
    },
    "canariasnoticias": {
        "nombre":  "Canarias Noticias",
        "color":   "#558b2f",
        "url":     "https://www.canariosnoticias.es",
        "rss": [],
        "tipo": "html_only",   # robots.txt bloquea el feed RSS
        "max_items": 25,
        "selectores": {
            "titular": "h2 a, h3 a, .entry-title a, article a",
            "resumen": ".entry-excerpt, .entry-summary, p.lead",
        },
        # AVISO (abril 2026): el sitio devuelve ECONNREFUSED de forma persistente.
        # Se mantiene en config para reactivar cuando el servidor vuelva online.
        # Total histórico scraping_log: 0 noticias desde el inicio del proyecto.
    },
    "canariasahora": {
        "nombre":  "Canarias Ahora",
        "color":   "#c62828",
        "url":     "https://www.eldiario.es/canariasahora/",
        "rss": [],
        "tipo": "html_only",   # La portada opera dentro de eldiario.es (React SPA)
        # React SPA: el DOM llega vacío con httpx → necesita Playwright
        "playwright": True,
        "max_items": 25,
        "selectores": {
            "titular": "p.title a, a.post-title, .ni-title a",
            "resumen": "p",
        },
        "html_url_regex": r"^https://www\.eldiario\.es/canariasahora/.+_\d+_\d+\.html(?:$|[?#])",
        "html_url_excludes": [
            "/busqueda/",
            "/autores/",
            "/contacto/",
            "/que_es/",
            "/aviso_legal/",
            "/politica_de_privacidad/",
        ],
    },
    "atlanticohoy": {
        "nombre":  "Atlántico Hoy",
        "color":   "#00695c",
        "url":     "https://www.atlanticohoy.com/",
        "rss": [],
        "tipo": "html_only",
        "max_items": 25,
        # CMS propio (abril 2026): el patrón principal de titulares usa c-item__title.
        # Se priorizan selectores verificados en DOM y se mantienen los anteriores como fallback.
        "selectores": {
            "titular": (
                ".c-item__title a, "
                ".c-highlight__item a, .c-ranking__link, .c-now-home__title-link, "
                "h2 a, h3 a"
            ),
            "resumen": ".c-item__subtitle, p",
        },
        # Patrón URL: /seccion/slug_XXXXXXXX_XX.html
        "html_url_regex": r"https://www\.atlanticohoy\.com/[\w-]+/[\w-]+_\d+_\d+\.html",
    },
    # ── Medios insulares ─────────────────────────────────────────────────────
    "eltime": {
        "nombre":  "El Time",
        "color":   "#d4a017",
        "url":     "https://eltime.es/",
        "rss": [],
        "tipo": "html_only",   # RSS existe pero devuelve feed vacío
        "max_items": 25,
        # Joomla 2.5/3.x — IceTheme Newsy 3 (it_newsy3)
        # Verificado abril 2026: allmode_title ya no existe en el DOM;
        # los titulares usan h3 y h4 con enlaces directos.
        "selectores": {
            "titular": "h3 a, h4 a",
            "resumen": "p",
        },
        # Patrón Joomla SEF: /categoria/ID-slug.html
        "html_url_regex": r"https://eltime\.es/.+/\d+-[\w-]+\.html",
    },
    "gomeraverde": {
        "nombre":  "Gomera Verde",
        "color":   "#388e3c",
        "url":     "https://gomeraverde.es/",
        "rss": [
            "https://gomeraverde.es/coverrss",
        ],
        "tipo": "rss+html",
        "max_items": 25,
        # folioePress CMS (CodeIgniter) — portada usa h3, no h1
        # Verificado en abril 2026: titulares en <h3> anidados en <a>
        "selectores": {
            "titular": "h3 a, h2 a",
            "resumen": "div.newsbody > p",
        },
        # Patrón: /art/{id}/{slug}
        "html_url_regex": r"https://gomeraverde\.es/art/\d+/[\w-]+",
    },
    "lancelotdigital": {
        "nombre":  "Lancelot Digital",
        "color":   "#bf360c",
        "url":     "https://www.lancelotdigital.com/",
        "rss": [
            "https://www.lancelotdigital.com/?format=feed&type=rss",
        ],
        "tipo": "rss+html",
        "max_items": 25,
        # Joomla 4.x/5.x — Verificado abril 2026: los selectores nspHeader y
        # mod-articles-category-title ya no están en el DOM. Los titulares usan
        # h3 > a directamente, con categorías en texto plano adyacente.
        "selectores": {
            "titular": "h3 a, h3.nspHeader a, a.mod-articles-category-title, h2 a",
            "resumen": "h4.nspText, p",
        },
        # Patrón: /{categoria}/{slug}
        "html_url_regex": r"https://www\.lancelotdigital\.com/[\w-]+/[\w-]+",
        "html_url_excludes": ["/component/", "/component/banners/"],
    },
    "elhierrohoy": {
        "nombre":  "El Hierro Hoy",
        "color":   "#5d4037",
        "url":     "https://elhierrohoy.es/",
        "rss": [
            "https://elhierrohoy.es/feed/",
        ],
        "tipo": "rss+html",
        "max_items": 20,
        # WordPress + Elementor Pro (Hello Elementor theme)
        # Verificado en abril 2026: los titulares usan h2, no h1.
        # Selector anterior (.elementor-widget-theme-post-title h1...) no coincidía.
        "selectores": {
            "titular": "h2.elementor-heading-title a, .elementor-heading-title a",
            "resumen": ".elementor-widget-theme-post-excerpt",
        },
        # Patrón WP: /{slug}/
        "html_url_regex": r"https://elhierrohoy\.es/[\w-]+/",
        "html_url_excludes": ["/category/", "/tag/", "/author/", "/page/", "/?columnas="],
    },
    "lavozdefuerteventura": {
        "nombre":  "La Voz de Fuerteventura",
        "color":   "#f9a825",
        "url":     "https://www.lavozdefuerteventura.com/",
        "rss": [
            "https://www.lavozdefuerteventura.com/rss/",
        ],
        "tipo": "rss+html",
        "max_items": 25,
        # OpenNemas CMS — Verificado abril 2026: las clases h2.title y div.data-title
        # ya no aparecen en el HTML renderizado. Se amplían selectores genéricos.
        # El RSS es la fuente principal; HTML es fallback complementario.
        "selectores": {
            "titular": "h2 a, h3 a, h2.title a, div.data-title a, .title a",
            "resumen": "div.summary, div.subtitle, p",
        },
        # Patrón: /articulo/{cat}/{slug}/{timestamp+id}.html
        "html_url_regex": r"https://www\.lavozdefuerteventura\.com/articulo/[\w-]+/[\w-]+/\d+\.html",
    },
}
