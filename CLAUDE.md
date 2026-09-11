# medios-odesocan · guía de trabajo

Observatorio de Medios de Canarias (ODESOCAN). Raspado de portadas y feeds de la
prensa canaria, clasificación multietiqueta en 15 temas de derechos sociales,
volcado a PostgreSQL/Supabase (`bd_odesocan`, esquema `medios`) y dashboard
estático en GitHub Pages.

El proyecto es **un instrumento de medida en ciencias de la comunicación**, no
solo un pipeline. Antes de tocar la ingesta o de calcular cualquier cifra, leer:

- [`docs/CUADERNO_METODOLOGICO.md`](docs/CUADERNO_METODOLOGICO.md) — qué mide el
  instrumento, qué puede medir y qué no. Segunda edición, septiembre de 2026.
- [`docs/estado-instrumentacion.md`](docs/estado-instrumentacion.md) — qué hay
  realmente en el código, el esquema y el corpus. Verificado el 2026-09-10.

Los cinco cambios de instrumentación (R1–R5) están implementados desde el
2026-09-10 y el corpus histórico quedó sellado el 2026-09-11, pero **el corpus
acumulado sigue siendo todo del régimen antiguo**: lo que el cuaderno da por
medible lo será a partir de la primera tirada del pipeline nuevo, no hacia
atrás. Cualquier afirmación sobre lo que el observatorio «ya mide» debe
comprobarse contra el segundo documento.

**La prueba de régimen ha cambiado.** El cuaderno dice que
`clasificador_version IS NULL` identifica el tramo antiguo; tras el sellado eso
ya no vale, porque todo el histórico lleva huella. Usar `fecha_pub_origen IS
NULL`, o la ausencia de observaciones para esa pieza.

## Reglas metodológicas de obligado cumplimiento

Valen tanto para el análisis en R como para cualquier cifra que se publique.

1. **La unidad es la pieza-en-portada**, no el artículo, no el acontecimiento y
   no la producción del medio. Declararlo así en cualquier publicación.
2. **Peso fraccionado (1/k) en toda cuota de saliencia.** El recuento pleno solo
   sirve para co-ocurrencia temática. La media es de 1,24 temas por pieza: la
   diferencia entre criterios llega al 25 % y altera rankings.
3. **Declarar siempre el denominador**: producción total de la cabecera, o
   agenda temática de ODESOCAN. Son dos cuotas distintas. Hoy solo es calculable
   la segunda.
4. **Nunca comparar volúmenes brutos entre cabeceras.** En el tramo antiguo las
   cuotas de raspado eran desiguales (30/25/20), así que el volumen medía la
   configuración del raspador. Solo son comparables las distribuciones internas.
   Y desde el alta de EFE, Europa Press y RTVC, recordar que **una agencia no es
   un diario**: su agenda alimenta a las demás, así que una convergencia alta
   con ellas no se interpreta como entre dos cabeceras que compiten.
5. **La agenda del sistema es la media no ponderada de las cuotas por cabecera**,
   nunca la agregación de piezas.
6. **`fecha_scrap` no es fecha de publicación.** Codifica el orden del
   diccionario de configuración: un análisis de liderazgo construido sobre ella
   «descubrirá» que la primera cabecera marca la agenda. Hoy no hay alternativa
   en el corpus, así que el análisis de precedencia está bloqueado.
7. **Reportar el sesgo del clasificador**: `peso_titulo` vale 4 en violencia de
   género y salud mental y 2 en política y medio ambiente, con umbral 2,6. Esos
   dos temas se activan con más facilidad. No es asimetría de la agenda de los
   medios.
8. **Encuadre solo con libro de códigos y α de Krippendorff ≥ 0,80.** Un tópico
   estadístico no es un marco. Sin fiabilidad intercodificadora, no se publica.
9. **No llamar priming a lo que no lo es.** Sin serie externa de opinión pública
   solo hay establecimiento de agenda; llamarlo así es una contribución legítima
   y honesta.
10. **Cualquier serie que cruce un cambio de instrumentación mide, en parte, el
    cambio del instrumento.** Advertirlo siempre.

Antes de cualquier análisis, ejecutar la consulta de auditoría del apartado 4.3
del cuaderno. Las proporciones se miden, no se suponen.

## Ficha técnica

Toda publicación derivada del corpus lleva la ficha del apartado 11 del
cuaderno: ventana y volumen por cabecera, régimen de medida, universo declarado
frente a efectivo, denominador, regla de ponderación, fiabilidad de la marca
temporal, cobertura de texto, versión del clasificador y, si hay encuadre, libro
de códigos y α obtenida. Citar el commit concreto.

## Mapa del repositorio

| Fichero | Función |
|---|---|
| `config.py` | `MEDIOS` (17 cabeceras, dos agencias y RTVC incluidas), `TEMAS` (15), `SCRAPER`, `USER_AGENTS` |
| `scraper.py` | Recolección RSS + HTML, extracción de texto, SQLite efímero |
| `clasificador.py` | Clasificación híbrida multietiqueta (keywords, lemas, URL, spaCy) |
| `supabase_loader.py` | Sincronización con `medios.noticias` por `psycopg2` |
| `scheduler.py` | Encadena scraping → sync → dashboard; captura excepciones sin propagarlas |
| `scripts/build_wordcloud_terms.py` | Agregado léxico ponderado en `medios.wordcloud_terms` |
| `index.html` | Dashboard autónomo; lee Supabase desde el navegador con la *anon* key |
| `scripts/reclasificar.py` | Sella el corpus con la versión del clasificador y mide su deriva |
| `tests/` | Comprueba que el pipeline registra lo que el cuaderno dice que registra |
| `supabase/esquema.sql` | Esquema del régimen nuevo, idempotente y comentado |

## Antes de tocar la ingesta

Cada columna del régimen nuevo sostiene una medida concreta, y quitarla o
dejar de escribirla no rompe nada visible: simplemente deja de ser calculable
algo que el cuaderno promete.

| Si cambias… | Se cae… |
|---|---|
| El descarte de piezas sin tema | El denominador, y con él toda saliencia relativa a la producción |
| La escritura en `observaciones` | Duración de la atención y prominencia |
| El caché del listado | La permanencia, que pasa a ser falsa sin previo aviso |
| La cadencia de tiradas | El grano de la permanencia: cualquier serie anterior deja de ser comparable |
| `fecha_pub_origen` | La distinción entre fecha real y hora del raspado |
| La huella del clasificador | La comparabilidad longitudinal del etiquetado |

Ejecuta `python -m unittest discover -s tests` antes de dar por buena una
modificación del scraper o del cargador.

## Convenciones

- Documentación y comentarios en español.
- El usuario trabaja principalmente en **R**; los ejemplos de análisis van en R
  salvo que se pida otra cosa. El pipeline es Python.
- `scheduler.py` no propaga errores: un fallo de sincronización deja el workflow
  en verde. Comprobar el log del job, no el aspa.
- La *anon* key de Supabase es pública y va en `index.html`. Nada sensible debe
  depender de ella; para escribir se usa la *service_role* key, solo en secrets.
