# medios-odesocan

Procesamiento textual para la word cloud del Observatorio de Medios.

## Enfoque

No se añade un backend nuevo de serving. Supabase sigue siendo la fuente y el destino:

1. GitHub Actions ejecuta el procesamiento.
2. El script lee noticias desde Supabase.
3. Calcula términos ponderando `titulo`, `resumen` y `contenido_limpio`.
4. Escribe el agregado en `medios.wordcloud_terms`.
5. El frontend puede consultar ya el agregado filtrado por `medio` y `tema`.

## Variables necesarias

Secrets de GitHub:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

Variables opcionales de GitHub:

- `SUPABASE_SOURCE_SCHEMA`
- `SUPABASE_SOURCE_TABLE`
- `SUPABASE_TARGET_SCHEMA`
- `SUPABASE_TARGET_TABLE`
- `WORDCLOUD_MAX_TERMS`
- `WORDCLOUD_MIN_DOC_FREQ`

## Configuración frontend

La nube del [index.html](/Users/cristiancpv/Documents/Playground/medios-odesocan/index.html) ya no calcula términos en cliente. Ahora espera un objeto global como este antes del script principal:

```html
<script>
window.__SUPABASE_CONFIG__ = {
  url: 'https://TU-PROYECTO.supabase.co',
  anonKey: 'TU_ANON_KEY',
  schema: 'medios',
  wordcloudTable: 'wordcloud_terms'
};
</script>
```

Si falta esa configuración, la tarjeta mostrará un mensaje explícito de configuración pendiente.

## Supabase

Ejecuta primero:

```sql
\i supabase/wordcloud.sql
```

La tabla destino queda con estos ejes:

- global: `medio = null`, `tema = null`
- por medio: `medio = x`, `tema = null`
- por tema: `medio = null`, `tema = x`
- por combinación: `medio = x`, `tema = y`

## Lógica textual

- `titulo` pesa `3`
- `resumen` pesa `2`
- `contenido_limpio` pesa `1`
- se generan unigramas y bigramas
- se calcula `score = tf * log(1 + N / df)`
- se guardan ejemplos de titulares por término

## Consulta esperada desde frontend

Ejemplo conceptual:

```sql
select *
from medios.wordcloud_terms
where medio is not distinct from :medio
  and tema is not distinct from :tema
order by score desc
limit 55;
```
