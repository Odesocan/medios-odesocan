"""
Persistencia.

    sqlite.py    base local `data/noticias.db` — búfer de trabajo
    postgres.py  sincronización con Supabase — el estado real

Conviene tener claro que en GitHub Actions la SQLite es EFÍMERA: el runner se
destruye al terminar, así que cada ejecución arranca con una base vacía. La
deduplicación real se hace preguntando a PostgreSQL qué `url_hash` ya existen.
En local, en cambio, la SQLite sí persiste y actúa como caché.
"""
