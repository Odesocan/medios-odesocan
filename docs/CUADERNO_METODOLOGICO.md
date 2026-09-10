# Cuaderno metodológico · Segunda edición

**Observatorio de Medios de Canarias**
*Agenda, encuadre y prioridad informativa en la prensa del archipiélago: qué mide el instrumento, qué puede medir y qué no*

| | |
|---|---|
| Investigación | ODESOCAN · Observatorio de Derechos Sociales de Canarias |
| Infraestructura | `medios-odesocan` · 17 cabeceras · 15 temas · PostgreSQL / Supabase |
| Periodo de referencia | Corpus desde el 16 de marzo de 2026 |
| Tipo de documento | Cuaderno metodológico · documento de trabajo interno |
| Revisión | Segunda edición, tras aplicar los cinco cambios de instrumentación |
| Fecha | Septiembre de 2026 |

> **Nota del repositorio.** Este fichero reproduce el cuaderno metodológico tal
> como lo redactó el equipo de investigación. Sus dictámenes describen el
> instrumento *previsto*. El estado verificado del código, del esquema y del
> corpus a 10 de septiembre de 2026 está en
> [`docs/estado-instrumentacion.md`](estado-instrumentacion.md), y no coincide
> con lo que este cuaderno da por aplicado. Léanse juntos.

---

## Resumen

El observatorio recoge la portada y los feeds de 17 cabeceras canarias —quince diarios digitales, dos agencias y la radiotelevisión pública—, clasifica cada pieza en 15 temas de derechos sociales y acumula el corpus en PostgreSQL. Este cuaderno traduce tres constructos clásicos de la investigación en comunicación —establecimiento de agenda, encuadre y priming— a indicadores calculables sobre esa base de datos concreta, y dictamina cuáles son medibles y cuáles no.

Esta es la segunda edición. La primera identificó cinco cambios necesarios en la instrumentación; los cinco se han aplicado, y el diagnóstico cambia en consecuencia. La agenda temática agregada y por cabecera es medible sin reservas, y con ella la prominencia y la duración de la atención, que antes se perdían en la ingesta. La agenda de atributos admite ya series temporales. El encuadre sigue exigiendo un libro de códigos y una prueba de fiabilidad intercodificadora que no existen. El priming sigue sin ser medible sin una serie externa de opinión pública. Y de los cuatro bloqueos que impedían responder quién habla primero, tres están levantados: queda identificar cuándo dos piezas hablan del mismo acontecimiento.

El corpus queda partido en dos regímenes de medida, y esa discontinuidad —descrita en el apartado 2.4— condiciona cualquier serie que cruce la fecha de cambio. Es la advertencia más importante de esta edición.

---

## 1 · Objeto y alcance del cuaderno

Este documento no describe la infraestructura técnica del observatorio —eso lo hace el Anexo I, que reproduce el índice técnico `ARQUITECTURA.md` del repositorio— sino su condición de instrumento de medida en ciencias de la comunicación. Responde a una pregunta previa a cualquier análisis: **¿qué inferencias soporta este corpus, y cuáles no?**

La necesidad de escribirlo nace de una asimetría habitual en los observatorios de medios construidos sobre raspado automatizado. La infraestructura produce cifras con facilidad —cuántas piezas, de qué medio, sobre qué tema— y esas cifras invitan a interpretaciones que el diseño muestral no sostiene. Un porcentaje bien calculado sobre un corpus mal delimitado sigue siendo un dato falso.

El cuaderno cubre tres constructos y una pregunta operativa:

- **Establecimiento de agenda** (*agenda setting*), en sus dos niveles: la saliencia de los temas y la saliencia de los atributos con que se construye cada tema.
- **Encuadre** (*framing*): los marcos interpretativos con que cada cabecera define un problema, atribuye causas y sugiere tratamientos.
- **Priming**: el traslado de la saliencia mediática a los criterios con que la ciudadanía evalúa a los actores políticos.
- **Prioridad informativa**: quién publica primero y quién sigue, es decir, el establecimiento de agenda inter-medios.

Cada uno se somete al mismo examen en tres pasos: qué exige el constructo, qué ofrece la base de datos, y qué distancia queda entre ambos. Cuando la distancia es salvable, se indica el cambio concreto que la salva.

---

## 2 · Qué observa realmente el instrumento

### 2.1 · La unidad de análisis

Cada fila de `medios.noticias` es una URL vista en la portada o el feed de una cabecera en un momento de observación. Conviene nombrar con precisión lo que eso es y lo que no es.

**No es el artículo**: `texto_full` lo aproxima, pero se trunca a 5.000 caracteres y su extracción puede fallar. **No es el acontecimiento**: un mismo hecho genera tantas piezas como cabeceras lo cubran, y esa multiplicidad es precisamente el objeto de estudio, no un problema a corregir. Y **no es la producción de la cabecera**: es lo que la cabecera destacó en el momento de la observación.

La unidad es, por tanto, **la pieza-en-portada**. Es una unidad legítima y teóricamente motivada —el establecimiento de agenda se ocupa justamente de las señales de relevancia que el medio ofrece a su público, y la portada es esa señal—, pero hay que declararla como tal y no confundirla con el volumen de publicación.

### 2.2 · Universo, muestra y cadencia

**Tabla 1. Parámetros del diseño muestral**

| Parámetro | Valor | Implicación metodológica |
|---|---|---|
| Cabeceras configuradas | 17 | Quince diarios digitales, dos agencias (Europa Press y EFE) y la radiotelevisión pública (RTVC). |
| Cabeceras activas | 15 | El Pueblo Canario y Canarias Noticias devuelven `ECONNREFUSED` de forma persistente: 0 piezas históricas. El universo efectivo es 15. |
| Cadencia | 4 ejecuciones diarias, cada 6 h | Cron a las 02, 08, 14 y 20 UTC. GitHub lo encola con retraso variable, así que son orientativas. |
| Cuota del listado | Sin tope | La portada se recorre entera. Los volúmenes vuelven a ser comparables entre cabeceras. |
| Cuota de texto completo | 15 artículos por cabecera y tirada | Solo lo gastan las piezas nuevas y con tema. Es el único recorte que queda, y afecta al encuadre, no a la saliencia. |
| Fuente | Feed RSS (7 cabeceras), portada HTML (las que no tienen feed) y API REST (RTVC) | Muestra de prominencia, no censo de producción. |
| Filtro de entrada | Ninguno | Las piezas sin tema se almacenan con `temas` vacío: son el denominador. Filtra la consulta, no la ingesta. |

*Fuente: elaboración propia a partir de `observatorio/config/`, `.github/workflows/scraping.yml` y `observatorio/recoleccion/orquestador.py`.*

Dos consecuencias se siguen directamente de esta tabla y conviene fijarlas antes de seguir.

**Primera**: las piezas que aparecen y desaparecen de portada dentro de un mismo ciclo de 24 horas son invisibles para el instrumento. El sesgo no es aleatorio, es sistemático a favor de las historias persistentes y en contra de las efímeras. Para el estudio de la agenda esto atenúa la rotación real del ciclo informativo.

**Segunda**: la cuota desigual (30 piezas para Canarias7, La Provincia, El Día y Diario de Avisos; 25 para la mayoría; 20 para El Hierro Hoy) hace que cualquier comparación de volumen bruto entre cabeceras mida la configuración del raspador, no la actividad del medio. Solo son comparables las distribuciones internas: qué proporción de lo que cada cabecera destaca corresponde a cada tema.

### 2.3 · El denominador: qué cambió y desde cuándo

En la primera edición este apartado documentaba la limitación central del instrumento: el clasificador puntuaba cada pieza contra los 15 temas y eliminaba la que no alcanzaba el umbral. El descarte no era una etiqueta, era un borrado.

La consecuencia era que la saliencia —una magnitud relativa por definición al total de la producción— no podía calcularse. No era posible afirmar «el 18 % de la agenda de Canarias7 fue vivienda», solo «el 18 % de su agenda relevante para ODESOCAN fue vivienda», que es otra cosa. Y una cabecera con mucha cobertura deportiva resultaba indistinguible de otra sin ella, porque a ambas se les amputaba el mismo tipo de contenido antes de contar.

> **Corregido, pero solo hacia delante.** Las piezas sin tema ya no se descartan: se almacenan con el array `temas` vacío y sin gastar una petición en su cuerpo. Filtra la consulta, y la vista pública del dashboard, no la ingesta.
>
> Pero el corpus acumulado hasta el cambio no tiene denominador y no puede tenerlo: lo que se descartó no se guardó en ninguna parte. De las 13.428 piezas históricas, solo 193 carecen de tema, y no porque el filtro dejara pasar poco, sino porque el resto nunca llegó a escribirse. Cualquier cuota calculada sobre el tramo antiguo sigue siendo relativa a la agenda de ODESOCAN, no a la producción del medio.

En la primera tirada real se puede ver la magnitud de lo que se perdía. Sobre El Hierro Hoy, 47 piezas en portada de las que 14 tenían tema: el 70 % del denominador era invisible. Sobre El Día, 68 de 107. Ese es el orden de lo que faltaba.

### 2.4 · La discontinuidad del instrumento

Es la advertencia más importante de esta edición, y afecta a cualquier serie temporal que se publique con estos datos.

Los cinco cambios de instrumentación no se aplicaron retroactivamente, porque en su mayoría no podían aplicarse: la información que ahora se registra sencillamente no se recogió antes. El corpus queda por tanto partido en dos regímenes de medida, y las variables nuevas están vacías en todo el tramo anterior.

**Tabla 2. Qué hay en cada régimen del corpus**

| Variable | Tramo antiguo (16 mar – 6 sep 2026) | Tramo nuevo |
|---|---|---|
| Piezas sin tema (denominador) | No se guardaron | Se guardan |
| Permanencia en portada | Sin registrar | Una observación por tirada |
| Posición en el listado | Sin registrar | Registrada |
| Sección propia del medio | 0 de 13.428 piezas | Registrada |
| Versión del clasificador | 0 de 13.428 piezas | Sellada |
| Procedencia de la fecha | 0 de 13.428 piezas | Registrada |
| Cuota de raspado | 20–30, desigual | Sin tope |
| Observaciones por día | 1 | 4 |
| Cabeceras | 12 con datos | 15 activas |

*Cifras verificadas contra el proyecto `bd_odesocan`. El tramo nuevo empieza con la primera ejecución del pipeline reinstrumentado.*

De aquí se siguen tres reglas prácticas que conviene fijar antes de escribir una sola línea de análisis:

- Una serie que cruce la fecha de cambio **mide, en parte, el cambio del instrumento**. El salto de volumen por cabecera —de unas 30 piezas diarias a más de 100— no es un cambio en la prensa canaria, es el fin del recorte del listado.
- El tramo antiguo sigue siendo utilizable, pero solo para lo que ya soportaba: cuotas temáticas dentro de la agenda de ODESOCAN, convergencia entre cabeceras y vocabulario por ámbito. No para saliencia relativa a la producción, ni para prominencia, ni para duración de la atención.
- Tres de las variables nuevas sí son recuperables hacia atrás y conviene hacerlo: la sección y la procedencia de la fecha se deducen de la URL sin ninguna petición, y la versión del clasificador se sella reclasificando el corpus. Las otras —denominador, permanencia y posición— no lo son.

Mientras el histórico no se selle, la comprobación de qué régimen tiene cada pieza es inmediata: `clasificador_version IS NULL` identifica el tramo antiguo.

---

## 3 · De la teoría al dato: mapa de operacionalización

La tabla siguiente es el núcleo del cuaderno. Cada fila recorre el camino completo desde el constructo teórico hasta la columna concreta que lo sostiene, y emite un dictamen sobre su viabilidad. Los dictámenes se refieren al tramo nuevo del corpus; para el antiguo hay que leerlos junto al apartado 2.4.

**Tabla 3. Constructos, indicadores y viabilidad**

| Constructo | Indicador | Dato que lo sostiene | Estado |
|---|---|---|---|
| Agenda, 1.er nivel · Saliencia temática | Cuota temática por cabecera y periodo, relativa a la producción | `noticias.temas`, `medio`, `fecha_scrap` | Disponible |
| Agenda, 1.er nivel · Diversidad | Entropía normalizada de la distribución temática | íd. | Disponible |
| Agenda, 1.er nivel · Convergencia | ρ de Spearman entre rankings temáticos de pares de cabeceras | íd. | Disponible |
| Agenda, 1.er nivel · Prominencia | Posición de la pieza en el listado de portada | `observaciones.posicion` | Disponible |
| Agenda, 1.er nivel · Duración de la atención | Cuántas tiradas aguanta una pieza en portada | `observaciones` (una fila por tirada) | Disponible |
| Agenda, 2.º nivel · Atributos | Vocabulario distintivo de cada cabecera dentro de un mismo tema | `wordcloud_terms` (medio × tema × periodo) | Disponible |
| Validez del clasificador | Contraste de los 15 temas contra la taxonomía nativa del medio | `noticias.seccion` | Disponible |
| Encuadre | Marcos genéricos y específicos del asunto | `texto_full` (5.000 car.) | Requiere protocolo |
| Priming | Traslado de la saliencia mediática a los criterios de evaluación pública | Ninguno: exige serie de opinión pública externa | Bloqueado |
| Agenda inter-medios · Prioridad | Quién publica primero una misma historia | Fecha y cadencia resueltas; falta agrupar piezas por acontecimiento | Requiere protocolo |

*Estado: «disponible» = calculable hoy; «requiere ajuste» = calculable tras un cambio menor documentado en el capítulo 10; «requiere protocolo» = el dato existe pero falta el instrumento de codificación; «bloqueado» = falta el dato.*

---

## 4 · Primer nivel: la agenda temática

El primer nivel del establecimiento de agenda mide qué asuntos reciben atención y en qué proporción. Es la formulación original de McCombs y Shaw (1972), y su operacionalización canónica —correlación de rangos entre la agenda del medio y la del público— sigue siendo la referencia. Aquí se aplica entre cabeceras, no entre medio y público, porque el instrumento observa medios.

### 4.1 · Decisión previa: el peso de las piezas multitema

El clasificador es multietiqueta: `temas` es un array y una pieza puede llevar varios temas. Antes de contar nada hay que decidir cómo pesa una pieza que pertenece a tres temas a la vez, y la decisión no es inocua.

- **Recuento pleno**: cada tema suma 1. Los totales por tema exceden el número de piezas. Es lo adecuado para analizar co-ocurrencia temática (qué temas viajan juntos).
- **Peso fraccionado**: cada tema suma 1/k, donde k es el número de temas de la pieza. Las cuotas suman 1 y son comparables entre cabeceras. Es lo adecuado para medir saliencia.

**La recomendación es peso fraccionado para toda cuota de saliencia, y declararlo.** La razón no es estética: las cabeceras difieren en su propensión al multietiquetado —depende de la longitud de titulares y entradillas—, de modo que el recuento pleno premia sistemáticamente a las que escriben titulares largos. En el corpus actual la media es de 1,25 temas por pieza clasificada, así que la diferencia entre ambos criterios es del orden del 25 % en los totales por tema: suficiente para alterar un ranking.

Hay además un **sesgo interno al clasificador** que conviene reportar. El parámetro `peso_titulo` vale 4 en violencia de género y salud mental, y 2 en política y medio ambiente. Con peso 4, una sola palabra clave en el titular basta para superar el umbral de 2,6. Eso hace que esos dos temas se activen con más facilidad que el resto: la decisión es deliberada —se prioriza no perder cobertura— pero introduce una asimetría en las cuotas que **no debe leerse como asimetría en la agenda de los medios**. Cualquier serie que compare temas entre sí debe advertirlo.

### 4.2 · Indicadores

**Tabla 4. Batería de indicadores del primer nivel**

| Indicador | Definición | Lectura |
|---|---|---|
| Cuota temática `S(m,t,p)` | Proporción de la agenda de la cabecera *m* en el periodo *p* dedicada al tema *t*, con peso fraccionado | La unidad básica. Comparable entre cabeceras. |
| Agenda del sistema `S(·,t,p)` | Media no ponderada de las cuotas de las cabeceras activas | No ponderar evita que las cuotas de raspado desiguales dominen el agregado. |
| Diversidad `H` normalizada | Entropía de Shannon de la distribución temática, dividida por ln(15) | 1 = atención repartida entre todos los temas; 0 = cabecera monotemática. |
| Convergencia `ρ` de Spearman | Correlación de rangos entre las cuotas temáticas de dos cabeceras | Matriz 12×12. Su agrupamiento jerárquico revela familias de agenda. |
| Distancia al sistema (Jensen–Shannon) | Divergencia entre la distribución de la cabecera y la del sistema | Identifica cabeceras con agenda propia frente a las que replican el consenso. |
| Duración de la atención `D(pieza)` | Número de tiradas consecutivas en que la pieza sigue en portada, sobre `observaciones` | La otra mitad de la saliencia. Con cuatro tiradas al día, el grano es de seis horas. |
| Prominencia `P(pieza)` | Mejor posición alcanzada en el listado, o media de posiciones ponderada por duración | Comparar solo dentro del mismo valor de `fuente`: la posición 3 de un feed no equivale a la 3 de una portada. |

Con k = 15 temas, una ρ de Spearman requiere \|ρ\| > 0,51 para ser significativa al 5 %. Con 12 cabeceras, la matriz tiene 66 pares: conviene corregir por comparaciones múltiples antes de interpretar celdas sueltas.

### 4.3 · Protocolo de cálculo

**Primer paso obligatorio, antes de cualquier análisis: auditar el corpus.** Esta consulta devuelve, por cabecera, el volumen, la fiabilidad de la marca temporal y la cobertura de texto completo.

```sql
-- Auditoría del corpus. Ejecutar contra medios.noticias por conexión directa.
-- Distingue los dos regímenes: clasificador_version IS NULL = tramo antiguo.
select
  medio,
  count(*)                                               as piezas,
  min(fecha_scrap)::date                                 as desde,
  max(fecha_scrap)::date                                 as hasta,
  count(*) filter (where clasificador_version is null)   as tramo_antiguo,
  count(*) filter (where cardinality(temas) = 0)         as sin_tema,
  count(*) filter (where fecha_pub_origen is not null
                     and fecha_pub_origen <> 'sintetica') as fecha_fiable,
  count(*) filter (where fecha_pub_origen = 'url')       as solo_precision_dia,
  count(texto_full)                                      as con_texto,
  round(100.0 * count(texto_full)
        / nullif(count(*), 0), 1)                        as pct_texto,
  count(distinct seccion)                                as secciones_propias,
  round(avg(cardinality(temas)), 2)                      as temas_por_pieza
from medios.noticias
group by medio
order by piezas desc;
```

Ninguna cifra de este cuaderno sustituye a esta consulta: las proporciones reales hay que medirlas, no suponerlas.

Una segunda consulta mide la duración de la atención, que es lo que aporta la tabla de observaciones:

```sql
-- Cuánto aguanta cada pieza en portada, y en qué posición.
select
  n.medio,
  n.titulo,
  count(o.id)                        as tiradas_en_portada,
  count(o.id) / 4.0                  as dias_aproximados,
  min(o.posicion)                    as mejor_posicion,
  min(o.observado_en)                as primera_vez,
  max(o.observado_en)                as ultima_vez
from medios.noticias n
join medios.observaciones o on o.url_hash = n.url_hash
where cardinality(n.temas) > 0
group by n.url_hash, n.medio, n.titulo
order by tiradas_en_portada desc
limit 50;
```

Con cuatro tiradas diarias, cada observación equivale a una ventana de seis horas. La división por 4 es una aproximación: una tirada puede fallar.

Con esas cifras sobre la mesa, el cálculo de los indicadores en R:

```r
library(DBI); library(dplyr); library(tidyr); library(tibble); library(lubridate)

con <- dbConnect(RPostgres::Postgres(),
                 host = Sys.getenv("SUPABASE_HOST"), port = 5432,
                 dbname = "postgres", user = Sys.getenv("SUPABASE_USER"),
                 password = Sys.getenv("SUPABASE_PASSWORD"), sslmode = "require")

piezas <- dbGetQuery(con, "select id, medio, titulo, temas, fuente,
                            fecha_pub, fecha_scrap from medios.noticias")

# 1. Formato largo con peso fraccionado (1/k por pieza)
largo <- piezas |>
  mutate(k = lengths(temas)) |>
  filter(k > 0) |>
  unnest_longer(temas) |>
  mutate(peso = 1 / k,
         mes  = floor_date(as.Date(fecha_scrap), "month"))

# 2. Cuota temática por cabecera y mes
cuotas <- largo |>
  group_by(medio, mes, temas) |>
  summarise(peso = sum(peso), .groups = "drop_last") |>
  mutate(cuota = peso / sum(peso)) |>
  ungroup()

# 3. Diversidad de la agenda (entropía normalizada)
diversidad <- cuotas |>
  group_by(medio, mes) |>
  summarise(H = -sum(cuota * log(cuota), na.rm = TRUE) / log(15), .groups = "drop")

# 4. Convergencia inter-cabeceras (matriz de Spearman)
M <- cuotas |>
  filter(mes == max(mes)) |>
  select(medio, temas, cuota) |>
  pivot_wider(names_from = medio, values_from = cuota, values_fill = 0) |>
  column_to_rownames("temas") |> as.matrix()
rho <- cor(M, method = "spearman")
familias <- hclust(as.dist(1 - rho), method = "average")

# 5. Distancia de cada cabecera a la agenda del sistema
js <- function(p, q) {
  m <- (p + q) / 2
  0.5 * sum(p * log(p / m), na.rm = TRUE) + 0.5 * sum(q * log(q / m), na.rm = TRUE)
}
sistema   <- rowMeans(M)
distancia <- apply(M, 2, js, q = sistema)
```

La agenda del sistema se calcula como **media no ponderada de las cuotas por cabecera**, no agregando piezas: agregar daría más peso a las cabeceras que más publican, que es una decisión distinta y hay que tomarla a conciencia.

Nótese el filtro `cardinality(temas) > 0` del paso 1: ahora hay que ponerlo explícitamente, porque las piezas sin tema están en la tabla. Y nótese que el denominador del paso 2 debe ser el total de piezas de la cabecera, no el total de piezas con tema, si lo que se quiere es saliencia relativa a la producción. Son dos cuotas distintas y conviene calcular ambas: su cociente es la proporción de la agenda del medio que cae dentro del ámbito de ODESOCAN, que es en sí mismo un indicador interesante.

---

## 5 · Segundo nivel: la agenda de atributos

El segundo nivel pregunta no qué temas reciben atención, sino **con qué rasgos** se construye cada tema. Es el puente entre el establecimiento de agenda y el encuadre, y es donde el observatorio está mejor equipado de lo que parece.

La tabla `medios.wordcloud_terms` almacena un agregado léxico ponderado con cuatro ámbitos precalculados, y uno de ellos —`medio:X|tema:Y`— es exactamente el diseño que exige el análisis de atributos: permite comparar cómo dos cabeceras lexicalizan el mismo asunto. El agregado pondera además el artículo completo, no solo el titular (título ×3, entradilla ×2, cuerpo ×1), de modo que capta vocabulario que no llega a portada.

### Indicadores

- **Solapamiento léxico**: índice de Jaccard sobre los N términos de mayor puntuación de dos ámbitos `medio:X|tema:Y` y `medio:Z|tema:Y`. Responde a: ¿hablan de vivienda con las mismas palabras?
- **Términos distintivos**: los que puntúan alto en el ámbito de una cabecera dentro de un tema y bajo en el ámbito del tema completo. Es el vocabulario propio de esa cabecera para ese asunto.
- **Anclaje cualitativo**: la columna `sample_titles` guarda hasta tres titulares por término, lo que permite volver del dato agregado al texto concreto sin una consulta adicional.

### Tres reservas, y una resuelta

**Resuelta**: el agregado ya tiene dimensión temporal. Antes se truncaba y se reconstruía sobre el corpus completo en cada ejecución, de modo que solo respondía a «qué palabras dominan el archivo entero»; la columna `generated_at` es la marca de construcción y se prestaba a leerla como un periodo. Ahora la tabla guarda el acumulado (`periodo = '__all__'`) y un corte mensual, hasta doce meses. El mes se deriva de `fecha_scrap`, que está siempre presente y es uniforme entre cabeceras, y no de `fecha_pub`, que tiene seis procedencias distintas; al agregar por mes la diferencia es despreciable. Con esto, la comparación de vocabulario entre cabeceras admite ya una dimensión longitudinal.

**Primera.** Las frecuencias están ponderadas. La columna `term_freq` incorpora ya el peso por campo, así que no es una frecuencia bruta. Para estadística léxica rigurosa —el log-odds con prior informativo de Monroe, Colaresi y Quinn (2008) es el estándar para identificar vocabulario distintivo— hay que recalcular desde `texto_full`, no partir del agregado.

**Segunda.** Los ámbitos pequeños son ruido. El pipeline conserva 80 términos por ámbito exigiendo que aparezcan en al menos 2 documentos. Para una combinación cabecera × tema con pocas piezas, ese umbral es demasiado laxo. Usar la columna `n_noticias` como filtro y descartar los ámbitos por debajo de unas 30 piezas.

**Tercera.** La similitud léxica no es identidad de encuadre. Dos cabeceras pueden compartir vocabulario y encuadrar en sentidos opuestos: «ocupación» aparece con la misma frecuencia en un texto que la presenta como delito y en otro que la presenta como síntoma de emergencia habitacional. El segundo nivel de agenda indica qué atributos se hacen accesibles; el encuadre exige el capítulo siguiente.

---

## 6 · Encuadre: protocolo en tres fases

Entman (1993) define el encuadre por cuatro funciones: definir un problema, diagnosticar sus causas, emitir un juicio moral y sugerir un tratamiento. Ninguna de las cuatro se deduce de un recuento de palabras. El encuadre es un constructo que exige codificación, y la codificación exige un instrumento con fiabilidad demostrada.

El corpus proporciona la materia prima —`texto_full` hasta 5.000 caracteres— pero no el instrumento. El protocolo siguiente lo construye en tres fases, y no debe saltarse ninguna.

**Fase A · Inductiva: descubrimiento de marcos candidatos.** Sobre el subconjunto de un tema, análisis de co-ocurrencia léxica o modelado de tópicos para generar hipótesis de marcos. El resultado de esta fase son candidatos, no mediciones: sirve para escribir el libro de códigos, no para publicar resultados. Confundir un tópico estadístico con un marco es el error más frecuente en la literatura reciente sobre encuadre computacional.

**Fase B · Deductiva: libro de códigos.** Se recomienda una estructura de dos capas. Como capa genérica, los cinco marcos de Semetko y Valkenburg (2000) —conflicto, interés humano, consecuencias económicas, moralidad y atribución de responsabilidad—, operacionalizados como veinte preguntas dicotómicas. Como capa específica del asunto, las cuatro funciones de Entman aplicadas al tema concreto, derivadas de la fase A. Esta arquitectura permite comparar entre temas (con la capa genérica, que es transversal) sin renunciar a la especificidad (con la capa propia de cada asunto).

**Fase C · Fiabilidad y medición.** Doble codificación de una submuestra aleatoria —como mínimo un 10 % del total o 100 unidades, lo que sea mayor— y cálculo de la α de Krippendorff. El umbral convencional es α ≥ 0,80; entre 0,667 y 0,80 los resultados solo admiten lectura exploratoria. Por debajo, hay que reescribir el libro de códigos, no publicar los datos.

Solo tras superar el umbral cabe escalar: codificación manual del total, o entrenamiento de un clasificador validado contra el patrón de referencia codificado a mano. En ese segundo caso, la métrica que se reporta es el acuerdo del clasificador con los codificadores humanos, no su exactitud interna.

### Restricciones del dato que condicionan el protocolo

- El truncamiento a 5.000 caracteres cubre la mayoría de las piezas de prensa canaria, pero mutila los reportajes largos. Hay que medir qué proporción del corpus llega al límite antes de decidir si afecta.
- Alrededor de una quinta parte de los textos se almacena con entidades HTML sin decodificar. El pipeline de la nube de palabras las decodifica al vuelo, pero la columna almacenada las conserva: cualquier codificación automática debe aplicar `unescape` antes de procesar.
- La cobertura de `texto_full` es parcial: la extracción se intenta siempre, pero puede fallar. La consulta de auditoría del apartado 4.3 devuelve el porcentaje real por cabecera. **Si la cobertura es desigual entre cabeceras, la comparación de encuadres queda confundida con la calidad de extracción.**

---

## 7 · Priming: qué falta para poder medirlo

Conviene empezar por una distinción que la literatura ha tardado en fijar. Siguiendo a Scheufele y Tewksbury (2007), el establecimiento de agenda y el priming operan por **accesibilidad** —qué asuntos vienen antes a la mente—, mientras que el encuadre opera por **aplicabilidad** —qué consideraciones se juzgan pertinentes para interpretar un asunto—. No son tres grados de lo mismo: son dos mecanismos psicológicos distintos.

El priming es, además, un constructo **de efectos**: afirma que la saliencia mediática de un asunto altera el peso que ese asunto tiene en la evaluación que la ciudadanía hace de los actores políticos (Iyengar y Kinder, 1987). Medirlo exige, por definición, datos de opinión pública. Ningún análisis de contenido, por sofisticado que sea, puede establecer un efecto de priming por sí solo.

Lo que el observatorio aporta es la variable independiente: una serie de saliencia temática por cabecera y periodo. Para cerrar el diseño hacen falta dos piezas más.

**Tabla 5. Requisitos para un diseño de priming**

| Pieza | Fuente candidata | Advertencia |
|---|---|---|
| Saliencia mediática | Este observatorio (capítulo 4) | Disponible tras el cambio R1. Serie mensual recomendada. |
| Saliencia pública | Barómetros del CIS: pregunta por los principales problemas | La submuestra canaria de un barómetro estatal ronda el centenar de casos. Error muestral alto: agregar por trimestre. |
| Criterios de evaluación | Estudios autonómicos del CIS y encuestas propias | Requiere ítems que midan a la vez actitud sobre el asunto y evaluación del gobierno. Su disponibilidad es irregular. |

Antes de comprometer recursos conviene verificar la disponibilidad y periodicidad reales de las series citadas para el ámbito canario.

El diseño de análisis, una vez reunidas las tres piezas, es un modelo de retardos distribuidos o una correlación cruzada desfasada: saliencia mediática en *t−1…t−k* frente a saliencia pública en *t*.

> **Versión mínima viable.** Sin la tercera pieza no hay priming, pero sí hay algo publicable y valioso: el primer eslabón de la cadena, es decir, el establecimiento de agenda a nivel del público —la correlación entre la saliencia mediática y la jerarquía de problemas que declara la ciudadanía canaria—. Es el diseño original de McCombs y Shaw, es replicable con dos de las tres piezas, y es una contribución legítima. Conviene nombrarlo por lo que es y no venderlo como priming.

---

## 8 · Quién habla primero: queda un bloqueo de cuatro

Es la pregunta que más interés despierta. La primera edición la declaraba imposible por cuatro motivos independientes. Tres se han levantado; el cuarto, que era el único que no figuraba en la hoja de ruta, sigue en pie.

### Levantado · La marca temporal ya no es sintética en la mayoría de las piezas

La fecha se busca ahora por cuatro vías. La más productiva resultó ser la más barata: varios medios la llevan embebida en la ruta de la URL (`/2026/09/07/`, `/2026-09-04/`, o un sello de catorce dígitos), y leerla de ahí no cuesta ninguna petición, así que funciona incluso para las piezas del denominador. Su precisión es de día. Las otras tres —JSON-LD del artículo, etiquetas `<meta>` y `<time>`— dan hora exacta pero exigen la descarga.

**Tabla 6. Cobertura de fecha real, medida contra la web**

| Cabecera | Antes | Después | Procedencia |
|---|---|---|---|
| La Provincia | 0 % | 100 % | URL (día) |
| El Día | 0 % | 100 % | URL (día) |
| EFE Canarias | 0 % | 100 % | URL (día) |
| RTVC | — | 100 % | API (hora exacta) |
| Canarias7 | 70 % | 70 % + artículo | Feed, y JSON-LD para el resto |

Las tres cabeceras de mayor difusión —las que más capacidad tienen de marcar agenda— pasan de no tener ninguna fecha fiable a tenerlas todas.

Igual de importante que la fecha es la columna `fecha_pub_origen`. Sin ella no se distingue una fecha real de la hora del raspado, y la primera edición describía tener que deducirlo por arqueología sobre `raw_json`. La regla de análisis es ahora explícita: filtrar por `fecha_pub_origen <> 'sintetica'`, y excluir además `'url'` si se ordena dentro de una jornada, porque esa vía solo tiene precisión de día.

### Levantado · `fecha_scrap` ya no es la única referencia temporal

> **La advertencia sigue vigente.** Las cabeceras se recorren secuencialmente en cada tirada, en el orden fijo del diccionario de configuración. `fecha_scrap` sigue codificando ese orden, no el de publicación, y un análisis de liderazgo construido sobre esa columna seguiría «descubriendo» que la primera cabecera del diccionario marca la agenda.
>
> Lo que cambia es que ya no hace falta usarla: para eso está ahora `fecha_pub` con su procedencia. La trampa no ha desaparecido, se ha vuelto evitable.

### Levantado · Hay resolución intradiaria

El scraping pasa de una a cuatro tiradas diarias, cada seis horas. Eso da grano de seis horas a la permanencia en portada y permite ver las piezas que aparecen y desaparecen dentro del mismo ciclo, que antes eran sencillamente invisibles.

El coste está contenido porque lo que se multiplica por cuatro es el listado —una petición por cabecera—, no la descarga de artículos: el scraper consulta primero qué piezas ya están en el corpus y se las salta. Sin esa consulta la cuadruplicación habría sido real, porque en integración continua la base local arranca vacía en cada tirada.

### En pie · «Misma historia» no es «mismo tema»

Quince temas son una rejilla demasiado gruesa para identificar un acontecimiento: dos piezas sobre vivienda pueden referirse a hechos sin relación alguna. Establecer precedencia exige agrupar a nivel de historia, y eso no es un problema de instrumentación sino de método.

El procedimiento estándar es similitud del coseno sobre TF-IDF de titular y entradilla, o incrustaciones de frase, con un umbral calibrado a mano contra una muestra codificada y una ventana temporal de agrupamiento. Es trabajo de análisis, no de pipeline: puede hacerse íntegramente en R o Python sobre el corpus ya existente, sin tocar el scraper.

**Lo que ya se puede hacer.** Con las fechas resueltas, un análisis de agenda inter-medios a escala diaria o semanal sobre las cuotas temáticas es viable hoy, mediante correlación cruzada desfasada, y sobre casi todo el universo en vez de sobre seis cabeceras.

Lo que sigue fuera de alcance es la precedencia a nivel de acontecimiento: quién dio primero esta noticia. Para eso hace falta el agrupamiento por historia, y conviene añadirlo a la hoja de ruta como el sexto cambio.

---

## 9 · Amenazas a la validez

Inventario actualizado. Las cuatro primeras de la edición anterior están resueltas para el tramo nuevo del corpus, pero ninguna lo está retroactivamente, y esa asimetría es la primera amenaza de esta lista.

**Tabla 7. Amenazas a la validez, por gravedad**

| # | Amenaza | Efecto sobre la inferencia | Gravedad |
|---|---|---|---|
| A1 | Discontinuidad del instrumento: los cinco cambios no son retroactivos | Una serie que cruce la fecha de cambio mide en parte el cambio del instrumento. El salto de volumen por cabecera no es un cambio en la prensa canaria. | Crítica |
| A2 | El tramo antiguo (16 mar – 6 sep 2026) no tiene denominador, ni permanencia, ni posición, y no puede tenerlos | Sobre él solo se sostiene lo que ya se sostenía: cuotas dentro de la agenda de ODESOCAN, convergencia y vocabulario. No saliencia relativa a la producción. | Crítica |
| A3 | El corpus histórico está sin sellar: 13.428 piezas con `clasificador_version` a NULL | No se sabe con qué versión del clasificador se etiquetaron. Subsanable ejecutando la reclasificación, que además mide la deriva. | Alta |
| A4 | Las piezas de portada sin fecha en la URL solo obtienen fecha real si se descarga el artículo | Afecta sobre todo a Canarias7. Las piezas del denominador de esa cabecera se quedan con marca sintética; queda visible en `fecha_pub_origen`. | Media |
| A5 | Dos cabeceras con cero piezas históricas | El universo efectivo es 15, no 17. Declararlo o retirarlas de la configuración. | Media |
| A6 | Muestra de prominencia: la parte alta de la portada, cuatro veces al día | Sesgo a favor de las historias persistentes, muy atenuado respecto a la observación diaria única, pero no eliminado. | Media |
| A7 | Cobertura de `texto_full` parcial (77 % del corpus) y truncada a 5.000 caracteres | Condiciona el análisis de encuadre. El presupuesto de 15 artículos por cabecera y tirada es ahora el único recorte del pipeline. | Media |
| A8 | El crecimiento del corpus se ha multiplicado | Del orden de 1.500 filas diarias de noticias más las observaciones. No es una amenaza a la validez sino a la continuidad: si la cuota de Supabase se agota, el pipeline falla en silencio. | Operativa |
| A9 | `robots.txt` desactivado y rotación de doce user-agents de navegador | No afecta a la validez estadística, pero sí a la publicabilidad: «rotamos doce user-agents» es difícil de escribir en un apartado de método. | Procedimental |

Sobre **A9** conviene decidir algo. La configuración desactiva el respeto a `robots.txt` con una justificación razonada y mantiene pausas de cortesía generosas, pero al pasar a cuatro tiradas diarias el volumen de peticiones se ha multiplicado, y la rotación de user-agents de navegador se lee como evasión de detección más que como investigación. La alternativa coherente con un observatorio que publica su metodología es identificarse con un agente propio y una dirección de contacto, asumiendo el riesgo de que alguna cabecera lo bloquee. Cualquier publicación derivada debería declarar la finalidad investigadora, la excepción de minería de textos y datos aplicable, el volumen real de peticiones y el hecho de que solo se almacenan titulares, entradillas y extractos.

---

## 10 · Hoja de ruta técnica

Los cinco cambios que proponía la primera edición están aplicados, junto con dos correcciones que aparecieron al verificarlos. Queda un sexto que no figuraba en aquella lista y que es ahora el único obstáculo técnico para el capítulo 8.

**Tabla 8. Estado de la hoja de ruta**

| | Cambio | Estado | Qué desbloqueó |
|---|---|---|---|
| R1 | Conservar las piezas sin tema | Aplicado | El denominador. Todo el capítulo 4. |
| R2 | Registrar la posición en portada | Aplicado | La prominencia. Quedó en la tabla de observaciones, no en `noticias`, porque la posición cambia cada día. |
| R3 | Versión del clasificador y reclasificación | Aplicado | La comparabilidad longitudinal. Falta ejecutarlo sobre el histórico. |
| R4 | Fecha de publicación real y su procedencia | Aplicado | El análisis temporal para las cabeceras sin feed. |
| R5 | Cadencia sub-diaria y corte temporal del agregado | Aplicado | La resolución intradiaria y las series de atributos. |
| R6 | Agrupamiento de piezas por acontecimiento | Pendiente | La precedencia a nivel de historia: quién dio primero esta noticia. Es trabajo de análisis, no de pipeline. |

R6 no figuraba en la primera edición: apareció al desglosar los cuatro bloqueos del capítulo 8, y es el único que no se resuelve tocando el scraper.

### Dos correcciones que salieron al verificar

Ninguna estaba prevista, y ambas afectaban a la validez de lo que se estaba midiendo.

- **Compresión brotli anunciada sin soporte.** El cliente pedía `Accept-Encoding: br` sin tener la librería instalada, así que ante una respuesta comprimida devolvía binario sin descomprimir, que superaba el control de longitud mínima y se cacheaba como si fuera HTML. EFE Canarias rendía cero por este motivo, sin ningún error visible. Pudo estar afectando de forma intermitente a otras cabeceras.
- **Listado de portada servido desde una caché de siete días.** En integración continua no mordía porque el runner es efímero, pero en local habría fabricado permanencia falsa en la tabla de observaciones nada más crearla.

### Lo que queda por decidir

- **Sellar el corpus histórico** con la reclasificación. Su modo en seco mide antes cuánta deriva hay, que es una cifra interesante por sí misma: dice cuánto se ha movido el instrumento desde marzo.
- **El user-agent**, que es una decisión editorial y no técnica (A9).
- **Las dos cabeceras muertas**: diagnosticarlas o retirarlas, para que el universo declarado y el efectivo coincidan.
- **Una política de retención** para `texto_full` y para los meses antiguos del agregado, antes de que la cuota de almacenamiento obligue a improvisarla.

---

## 11 · Ficha técnica reproducible

Lo que debe acompañar a cualquier publicación derivada de este corpus. No es burocracia: la mitad de estos campos son los que permiten a un lector externo saber qué significan las cifras.

- Ventana temporal del corpus y número de piezas, por cabecera.
- **Régimen de medida**: si el análisis usa el tramo antiguo, el nuevo o ambos, y cómo se trata la discontinuidad del apartado 2.4.
- Universo declarado (17) y universo efectivo (15), nombrando las cabeceras excluidas y el motivo.
- **Naturaleza del denominador**: producción total de la cabecera, o agenda temática de ODESOCAN. Son dos cuotas distintas.
- **Regla de ponderación** de piezas multitema: recuento pleno o peso fraccionado.
- Fiabilidad de la marca temporal, desglosada por `fecha_pub_origen`, distinguiendo las de precisión de día.
- Si el análisis usa permanencia o posición: número de tiradas diarias en el periodo analizado, porque el grano depende de ello.
- Cobertura de texto completo por cabecera, si el análisis usa el cuerpo del artículo.
- Versión del clasificador (`clasificador_version`) presente en el corpus analizado, y si se reclasificó o se arrastran etiquetas de versiones anteriores.
- Para el segundo nivel de agenda: si se usa el acumulado o el corte mensual del agregado, y cuántos meses cubre.
- Para análisis de encuadre: libro de códigos completo, número de codificadores, tamaño de la submuestra de fiabilidad y α de Krippendorff obtenida.
- Declaración ética y jurídica sobre la recolección automatizada, incluido el volumen real de peticiones.

El repositorio es parte de la ficha técnica. El código que produjo las cifras está versionado en `github.com/Odesocan/medios-odesocan`, y citar el commit concreto convierte una afirmación en una afirmación verificable.

---

## 12 · Referencias

**Establecimiento de agenda y priming**

- McCombs, M. E., y Shaw, D. L. (1972). The agenda-setting function of mass media. *Public Opinion Quarterly*, 36(2), 176–187.
- Iyengar, S., y Kinder, D. R. (1987). *News That Matters: Television and American Opinion*. University of Chicago Press.
- Scheufele, D. A., y Tewksbury, D. (2007). Framing, agenda setting, and priming: The evolution of three media effects models. *Journal of Communication*, 57(1), 9–20.
- Vliegenthart, R., y Walgrave, S. (2008). The contingency of intermedia agenda setting: A longitudinal study in Belgium. *Journalism & Mass Communication Quarterly*, 85(4), 860–877.

**Encuadre**

- Entman, R. M. (1993). Framing: Toward clarification of a fractured paradigm. *Journal of Communication*, 43(4), 51–58.
- Semetko, H. A., y Valkenburg, P. M. (2000). Framing European politics: A content analysis of press and television news. *Journal of Communication*, 50(2), 93–109.

**Método y medición**

- Krippendorff, K. (2004). *Content Analysis: An Introduction to Its Methodology* (2.ª ed.). Sage.
- Monroe, B. L., Colaresi, M. P., y Quinn, K. M. (2008). Fightin' words: Lexical feature selection and evaluation for identifying the content of political conflict. *Political Analysis*, 16(4), 372–403.
- Boydstun, A. E., Bevan, S., y Thomas, H. F. (2014). The importance of attention diversity and how to measure it. *Policy Studies Journal*, 42(2), 173–196.

**Documentación del proyecto**

- ODESOCAN (2026). *Anexo I · Arquitectura técnica del observatorio*. Reproducción del índice técnico `ARQUITECTURA.md` del repositorio `medios-odesocan`.
- ODESOCAN (2026). `medios-odesocan`: `db/esquema.sql` y `db/wordcloud.sql`. Esquema versionado de la base de datos del observatorio.
- ODESOCAN (2026). `medios-odesocan`: `README.md`. Estado operativo de los pipelines y decisiones de diseño.

*Las referencias académicas son citas canónicas de la disciplina; conviene cotejarlas con los originales antes de incorporarlas a una publicación.*
