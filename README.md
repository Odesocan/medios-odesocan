# medios-odesocan

Observatorio de medios canarios de ODESOCAN: scraping diario de la prensa
canaria, clasificación temática y volcado a Supabase, con un dashboard estático
publicado en GitHub Pages.

## Pipelines

| Workflow | Fichero | Cadencia | Estado |
|---|---|---|---|
| Scraping medios canarios | `.github/workflows/scraping.yml` | diaria, 10:00 UTC | operativo |
| Build Wordcloud Terms | `.github/workflows/build-wordcloud.yml` | diaria, 12:00 UTC | operativo |
| Detectar declaraciones | `.github/workflows/build-declaraciones.yml` | diaria, 13:30 UTC | pendiente de aplicar el SQL |

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

### 4. Detector de declaraciones

El observatorio no sólo mide quién habla primero o cómo se enmarca un tema:
también localiza **qué ha afirmado cada cargo público** y deja esas
afirmaciones en una cola de trabajo.

La regla que ordena el diseño entero: **la detección es automática, el
veredicto es humano.** El pipeline nunca dice si algo es cierto o falso. Sólo
señala «esto lo dijo tal cargo, aquí, y contiene una cifra que se puede
contrastar». Quien verifica es una persona.

`declaraciones.py` reconoce al emisor **por su cargo**, no por una lista de
nombres. `la consejera de Sanidad` o `el alcalde de Arrecife` son patrones
estables; un censo nominal habría que rehacerlo con cada remodelación de
gobierno. Cuando el nombre aparece en aposición (`el presidente del Cabildo de
La Palma, Fulana de Tal, aseguró…`) se recoge, y de ahí sale
`medios.actores_candidatos`: el censo se cura desde el corpus en vez de
teclearlo.

Extrae las cuatro formas en que la prensa atribuye habla:

| Forma | Ejemplo |
|---|---|
| `titular` | `Fulana: "Las listas de espera han bajado un 12%"` |
| `directa` | `"El paro ha caído un 8,4%", aseguró la consejera de Empleo` |
| `indirecta` | `La consejera de Sanidad asegura que hay 400 camas nuevas` |
| `pospuesta` | `Las urgencias crecieron un 30%, según el consejero de Sanidad` |

Dos señales deciden qué llega a la cola:

- **Fuerza asertiva del verbo.** `cifra`, `asegura` o `niega` son aserciones y
  se pueden contrastar. `lamenta` o `celebra` son valoraciones y `exige` es una
  demanda: no hay nada que verificar en ellas. `promete` y `garantiza` abren
  una vía distinta, la de seguimiento de promesas, que se verifica cuando vence
  el plazo.
- **Anclajes verificables dentro de la cita**: porcentajes, cifras, magnitudes,
  unidades de servicio público (plazas, camas, listas de espera), rankings,
  comparaciones, plazos, cuantificadores absolutos y atribuciones causales. Una
  aserción sin ningún anclaje no entra: contrastarla sería una discusión, no
  una verificación.

De ahí sale `prioridad` (0-100), que es un **orden de trabajo sugerido, no una
medida de gravedad ni de verosimilitud**. Nada en el pipeline evalúa si lo
dicho es verdad.

#### Falsos positivos

El error caro de este detector no es dejar escapar una declaración: es
**atribuir a alguien algo que no dijo**. `tests/test_declaraciones.py` cubre esa
familia de casos —una cita seguida de otro cargo en la frase siguiente, un
encabezado de sección con dos puntos (`Canarias: las claves de la semana`), un
apellido suelto sin comillas, un entrecomillado de matiz (`el "efecto
llamada"`)— y el workflow **no escribe nada si esas pruebas fallan**. Al
ajustar umbrales, esas son las pruebas que no se relajan.

#### Qué es público y qué no

`medios.declaraciones` tiene RLS con una única política de lectura:
`estado = 'publicada'`. La cola pendiente **no sale al exterior**, y
`medios.actores_candidatos` tampoco tiene política ninguna, así que sólo la ve
`service_role`. Publicar una lista de afirmaciones de personas identificables,
marcadas por una heurística como «verificables» y sin que nadie las haya
comprobado, sería difundir una acusación que no ha revisado nadie.

La salida pública es `medios.v_declaraciones_publicas`: sólo filas con
veredicto cerrado. Dos restricciones de tabla lo garantizan: no hay veredicto
sin `revisado_por` y `revisado_en`, y no hay estado `publicada` sin veredicto.

#### Reproceso sin perder trabajo

`scripts/build_declaraciones.py` hace upsert **sólo de las columnas de
detección** (la lista está explícita en `COLUMNAS_DETECCION`). PostgREST
actualiza en el conflicto únicamente las columnas del payload, así que
`estado`, `veredicto`, `fuentes` y el resto del bloque humano quedan intactos.
Reprocesar el corpus entero tras tocar el detector es seguro: lo descartado
sigue descartado y lo publicado sigue publicado. La clave `hash_declaracion`
cuelga del `url_hash` de la noticia y del texto normalizado de la cita, no de
la posición en el artículo.

#### Aprovisionamiento

1. **Aplicar `supabase/declaraciones.sql`** en el proyecto. Crea las tres
   tablas, las dos vistas, las políticas RLS y
   `public.truncate_actores_candidatos`. Esta función no recibe esquema ni
   tabla por parámetro, a diferencia de `truncate_wordcloud_terms`: trunca una
   tabla escrita en el cuerpo, de modo que aunque alguien logre ejecutarla no
   puede vaciar ninguna otra.
2. **Secrets**: los mismos que la word cloud, `SUPABASE_URL` y
   `SUPABASE_SERVICE_ROLE_KEY`. Ya están configurados. Si faltan, el job se
   omite y explica el motivo en el resumen, igual que el de la word cloud.
3. **Primera pasada**: lanzar el workflow a mano con `dias = 0` para recorrer
   todo el histórico. Después, la ejecución programada trabaja sobre una
   ventana de 45 días.

Variables opcionales (*repository variables*): `DECLARACIONES_MIN_PRIORIDAD`
(`25`), `DECLARACIONES_DIAS` (`45`), `DECLARACIONES_CLASIFICAR_CITA` (`1`).
La última desactiva la reclasificación temática de cada cita, que es la parte
cara porque carga spaCy; con ella apagada se conservan igualmente los temas de
la noticia y el área del cargo.

#### Pendiente

- **Registro curado.** `medios.actores` está vacío: aporta partido y periodo en
  el cargo, que no se deducen del texto. Se rellena a mano revisando
  `medios.actores_candidatos`, que el pipeline reconstruye en cada pasada.
- **Interfaz de revisión.** Hoy la cola se consulta por SQL contra
  `medios.v_cola_verificacion`. Cerrar un veredicto es un `UPDATE` a mano.
- **Tarjeta en el dashboard.** `index.html` no lee todavía
  `medios.v_declaraciones_publicas`. No se ha añadido porque no hay ninguna
  verificación publicada que mostrar.
- **Fuentes primarias.** Contrastar contra ISTAC, el Servicio Canario de Salud
  o los presupuestos autonómicos sigue siendo trabajo manual. El detector
  marca *qué* hay que contrastar, no *contra qué*.

## Desarrollo local

```bash
pip install -r requirements-ci.txt
python -m spacy download es_core_news_md
python scheduler.py --run-now      # scraping + sync + dashboard
python generate_dashboard.py --dry-run

pip install pytest
python -m pytest tests/ -q                              # tests del detector
python scripts/build_declaraciones.py --dias 7 --dry-run  # cola sin escribir
```

`requirements.txt` solo contiene el cliente `supabase`, que es lo único que
necesita `scripts/build_wordcloud_terms.py`. El resto del pipeline usa
`requirements-ci.txt`.
