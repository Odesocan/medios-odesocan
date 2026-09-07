"""
Parámetros de comportamiento del scraper y pool de User-Agents.
"""
# ── Configuración del scraper ─────────────────────────────────────────────────
SCRAPER = {
    # Rango de espera entre peticiones (segundos) — se elige aleatoriamente
    "delay_min": 1.5,
    "delay_max": 5.0,
    # Probabilidad (0-1) de insertar una pausa larga ("el usuario se distrae")
    "pausa_larga_prob": 0.12,
    # Rango de duración de la pausa larga (segundos)
    "pausa_larga_rango": (8, 22),
    # Timeout por petición (segundos)
    "timeout": 15,
    # Máximo de reintentos ante error 5xx o timeout
    "max_reintentos": 3,
    # Máximo de noticias a guardar por medio y ejecución
    "max_items_por_medio": 50,
    # Días que se conserva el caché HTML
    "cache_ttl_dias": 7,
    # robots.txt desactivado: monitoreo académico con 1 ejecución/día,
    # menos tráfico que un lector humano
    "respetar_robots": False,
}

# Pool de User-Agents realistas (navegadores actuales, distintos SO)
# Actualizado abril 2026: Chrome 133-134, Firefox 136, Safari 18, Edge 134
USER_AGENTS = [
    # Chrome en Windows (versiones 133-134)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.141 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.165 Safari/537.36",
    # Chrome en macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_3_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.165 Safari/537.36",
    # Firefox en Windows (versiones 135-136)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:136.0) Gecko/20100101 Firefox/136.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0",
    # Firefox en macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15.3; rv:136.0) Gecko/20100101 Firefox/136.0",
    # Safari en macOS (versión 18)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_3_2) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.3.2 Safari/605.1.15",
    # Edge en Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36 Edg/134.0.3124.72",
    # Chrome en Linux (Ubuntu)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.6998.88 Safari/537.36",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
]
