# medios-odesocan

Observatorio de medios canarios de ODESOCAN: scraping diario de la prensa
canaria, clasificación temática y volcado a Supabase, con un dashboard estático
publicado en GitHub Pages.

## Pipelines

| Workflow | Fichero | Cadencia | Estado |
|---|---|---|---|
| Scraping medios canarios | `.github/workflows/scraping.yml` | diaria, 10:00 UTC | operativo |
| Build Wordcloud Terms | `.github/workflows/build-wordcloud.yml` | diaria, 12:00 UTC | operativo |

GitHub encola los `schedule` con retraso variable: la hora real de arranque
puede desplazarse varias horas respecto al cron. Es comportamiento de la
plataforma, no un fallo del repositorio.

### 1. Scraping diario

`scheduler.py --run-now` encadena:

1. `scraper.py` — recorre los medios de `config.py` (RSS + HTML), extrae los
   artículos y los guarda en SQLite (`data/noticias.db`, efímero en CI).
2. `clasificador.py` — asigna temas; las noticias sin tema se descartan.
3. `supabase_loader.py` — sincroniza lo nuevo contra `medios.noticias` en
   Supabase por conexión Postgres directa (`psycopg2`).
4. `generate_dashboard.py` — ver más abajo.

Secrets que necesita (ya configurados): `SUPABASE_HOST`, `SUPABASE_PORT`,
`SUPABASE_DBNAME`, `SUPABASE_USER`, `SUPABASE_PASSWORD`, `SUPABASE_SSLMODE`,
`SUPABASE_SCHEMA`.

`scheduler.py` captura las excepciones de cada fase y las registra sin
propagarlas: un fallo de sincronización **no** pone el workflow en rojo. Si algo
va mal, se ve en el log del job, no en el aspa roja.

### 2. Dashboard (`index.html`)

`index.html` es autónomo: obtiene los datos en el navegador desde la vista
pública `v_noticias_medios` de Supabase (con la *anon* key) y calcula ahí mismo
los agregados de medio, tema y actividad horaria.

La nube de palabras es la excepción: lee el agregado `medios.wordcloud_terms`
(ver más abajo), que pondera el artículo completo en vez de solo el titular.
`drawWC()` traduce los filtros de medio y tema al `scope_key` correspondiente,
pide ese ámbito bajo demanda y lo cachea. El filtro de fechas no interviene,
igual que antes: `filtNW()` nunca ha filtrado por fecha. Si el agregado no
responde o no tiene filas para el ámbito activo, la tarjeta recurre al cálculo
en cliente sobre los titulares y lo indica en su subtítulo, de modo que sigue
mostrando algo aunque el pipeline se rompa.

Por eso `generate_dashboard.py`, que inyectaba un bloque estático
`const MM=[…] … const NW=[…];` en el HTML, ya no tiene nada que reescribir: ese
bloque desapareció del fichero. El script lo detecta y lo registra como «sin
cambios» en lugar de dar un éxito que no ha ocurrido. Se mantiene por si se
vuelve a un dashboard con datos embebidos.

### 3. Word cloud agregada

`scripts/build_wordcloud_terms.py` calcula un agregado textual ponderado
(`titulo` ×3, `resumen` ×2, `contenido_limpio` ×1; unigramas y bigramas;
`score = tf · log(1 + N/df)`) y lo escribe en `medios.wordcloud_terms`, con
cuatro ejes de agrupación:

- global: `medio = null`, `tema = null`
- por medio: `medio = x`, `tema = null`
- por tema: `medio = null`, `tema = x`
- por combinación: `medio = x`, `tema = y`

Aprovisionado y verificado el 2026-08-29: primera ejecución correcta, 13.903
filas en 200 ámbitos sobre 12.664 noticias.

1. **Secrets del repositorio** — `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`,
   añadidos. Se configuran en *Settings → Secrets and variables → Actions*.
   La segunda debe ser la *service_role* key (el script escribe en la base de
   datos y necesita saltarse RLS), nunca la *anon* key.
2. **Esquema en Supabase** — `supabase/wordcloud.sql` aplicado. Crea
   `medios.wordcloud_terms` con RLS y lectura pública, su índice, la función
   `public.truncate_wordcloud_terms` restringida a `service_role`, y los grants
   de `service_role` sobre el esquema `medios`, que no existían.
3. **Consumo desde el frontend** — conectado. `drawWC()` en `index.html` lee
   `medios.wordcloud_terms` por REST con la *anon* key, que puede hacerlo
   gracias a la política `lectura_publica_wordcloud_terms`. La tabla vive en el
   esquema `medios`, así que la petición necesita la cabecera
   `Accept-Profile: medios`; sin ella PostgREST responde 404 (PGRST205).

Si falta alguno de los secrets, el workflow omite el paso de build y explica el
motivo en el resumen del job, en lugar de fallar.

Sobre la calidad de los términos: `texto_full` llega con entidades HTML sin
decodificar en cerca de una quinta parte de los artículos, así que `tokenize()`
las decodifica antes de segmentar. Sin ese paso, los términos con más score
eran `oacute`, `aacute`, `iacute` y `nbsp`. Queda margen de ajuste editorial en
`SPANISH_STOPWORDS`: aún asoman palabras vacías como `durante` o `gran`.

La función de truncado es `security definer` y recibe esquema y tabla por
parámetro, así que puede truncar cualquier tabla. No basta con revocarla de
`PUBLIC`: Supabase concede `EXECUTE` explícitamente a `anon` y `authenticated`
sobre las funciones nuevas de `public`, y la *anon* key de este proyecto es
pública. El fichero SQL revoca ambas por separado; si se recrea la función,
hay que volver a revocarlas.

Variables opcionales (como *repository variables*, con estos valores por
defecto): `SUPABASE_SOURCE_SCHEMA` (`medios`), `SUPABASE_SOURCE_TABLE`
(`noticias`), `SUPABASE_TARGET_SCHEMA` (`medios`), `SUPABASE_TARGET_TABLE`
(`wordcloud_terms`), `WORDCLOUD_MAX_TERMS` (`80`), `WORDCLOUD_MIN_DOC_FREQ`
(`2`).

## Desarrollo local

```bash
pip install -r requirements-ci.txt
python -m spacy download es_core_news_md
python scheduler.py --run-now      # scraping + sync + dashboard
python generate_dashboard.py --dry-run
```

`requirements.txt` solo contiene el cliente `supabase`, que es lo único que
necesita `scripts/build_wordcloud_terms.py`. El resto del pipeline usa
`requirements-ci.txt`.
