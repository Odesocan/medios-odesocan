"""
Recolección de noticias.

    clientes.py     HTTP con caché y reintentos (httpx) y Chromium (Playwright)
    rss.py          feeds RSS/Atom — la fuente más fiable
    portada.py      titulares de la portada: selectores CSS + JSON-LD de respaldo
    articulo.py     texto completo del artículo
    orquestador.py  encadena todo lo anterior medio a medio

La estrategia es en cascada: RSS primero, portada HTML si no hay feed o para
complementarlo, y JSON-LD como red de seguridad cuando un medio cambia de
plantilla y los selectores CSS dejan de encontrar nada.
"""
