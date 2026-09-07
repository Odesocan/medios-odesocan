"""
Publicación del dashboard.

    dashboard.py  regeneración del HTML con datos embebidos — LEGADO

Desde que `index.html` carga sus datos de Supabase en el navegador, el bloque
estático que este módulo reescribía ya no existe en el fichero. `generar_html()`
lo detecta y devuelve False ("sin cambios") en lugar de anunciar un éxito que no
ha ocurrido. Se conserva por si se vuelve a un dashboard con datos embebidos.
"""
