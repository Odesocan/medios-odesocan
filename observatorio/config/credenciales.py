"""
Conexión a Supabase (PostgreSQL directo, vía pooler).
"""

import os
# ── Supabase ──────────────────────────────────────────────────────────────────
# La contraseña se lee de la variable de entorno SUPABASE_PASSWORD.
# En GitHub Actions se inyecta como secret; en local puedes definirla
# en un fichero .env o dejarla como fallback aquí (solo para desarrollo).
SUPABASE = {
    "host":     os.getenv("SUPABASE_HOST", "aws-1-eu-west-1.pooler.supabase.com"),
    "port":     int(os.getenv("SUPABASE_PORT", "5432")),
    "dbname":   os.getenv("SUPABASE_DBNAME", "postgres"),
    "user":     os.getenv("SUPABASE_USER", "postgres.kdpsjutsgvghdtzoskkg"),
    "password": os.getenv("SUPABASE_PASSWORD", ""),
    "sslmode":  os.getenv("SUPABASE_SSLMODE", "require"),
    "schema":   os.getenv("SUPABASE_SCHEMA", "medios"),
}
