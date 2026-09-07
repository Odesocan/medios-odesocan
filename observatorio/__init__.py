"""
Observatorio de medios canarios de ODESOCAN.

El paquete está dividido por capas; cada subpaquete corresponde a una etapa
del pipeline y puede leerse de forma independiente:

    config/         qué medios y qué temas se observan, y con qué parámetros
    comun/          utilidades transversales (logging, normalización de texto)
    recoleccion/    descarga de RSS, portadas HTML y artículos
    clasificacion/  asignación de temas a cada noticia
    almacenamiento/ SQLite local y sincronización con PostgreSQL (Supabase)
    agregados/      cálculo de la nube de palabras
    publicacion/    generación del dashboard (legado)

Los puntos de entrada ejecutables viven en `bin/`, fuera del paquete.
"""
