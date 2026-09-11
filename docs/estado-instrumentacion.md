# Estado verificado de la instrumentación

**Última verificación:** 11 de septiembre de 2026 (alta de agencias y RTVC)
**Verificado contra:** árbol de trabajo de `medios-odesocan` (rama `claude/admiring-fermat-dv7g64`) y proyecto Supabase `bd_odesocan` (`kdpsjutsgvghdtzoskkg`).

Este documento acompaña a [`CUADERNO_METODOLOGICO.md`](CUADERNO_METODOLOGICO.md).
El cuaderno describe el instrumento previsto; esto describe el que hay.

## Diagnóstico en una frase

Los cinco cambios R1–R5 están **implementados en el código y presentes en el
esquema**, y el corpus histórico está **sellado** con la versión del
clasificador. Pero el tramo nuevo del corpus **no ha empezado**: las 13.761
piezas acumuladas siguen sin denominador, sin permanencia, sin posición y sin
fecha real, y lo seguirán estando hasta la primera tirada del pipeline
reinstrumentado.

> **Ojo con la prueba de régimen.** El cuaderno dice, en su apartado 2.4, que
> `clasificador_version IS NULL` identifica el tramo antiguo. Desde el sellado
> del 11 de septiembre de 2026 eso **ya no es cierto**: las 13.761 piezas
> antiguas llevan huella. La prueba correcta es ahora
> `fecha_pub_origen IS NULL`, que el pipeline nuevo escribe siempre, o la
> ausencia de filas en `medios.observaciones` para esa pieza.

## 1 · Los tres planos, por separado

| Plano | Estado |
|---|---|
| Esquema Supabase | Régimen nuevo. `noticias.seccion`, `noticias.clasificador_version`, `noticias.fecha_pub_origen`, `medios.observaciones` y `wordcloud_terms.periodo` existen, con sus comentarios de columna, sus índices y su restricción única `(url_hash, run_id)`. |
| Código del pipeline | Régimen nuevo. R1–R5 implementados y con comprobaciones automáticas en `tests/`. |
| Corpus | Régimen antiguo al 100 %, pero sellado: las 13.761 piezas llevan la huella `v2-29e00cc2d46f-es_core_news_md`. Ninguna tiene todavía fecha real ni observación de portada. |

## 2 · Hoja de ruta

| | Cambio | Esquema | Código | Dónde |
|---|---|---|---|---|
| R1 | Conservar las piezas sin tema | Listo | Listo | `scraper.py` (`guardar_noticia`, bucle de `scrapear_medio`), `supabase_loader.py` |
| R2 | Registrar posición y permanencia en portada | Listo | Listo | `scraper.py` (`registrar_observacion`), `supabase_loader.py` (`sincronizar_observaciones`) |
| R3 | Versión del clasificador y reclasificación | Listo | Listo, y **aplicado sobre el histórico el 2026-09-11** | `clasificador.py` (`version_clasificador`), `scripts/reclasificar.py` |
| R4 | Fecha de publicación real y su procedencia | Listo | Listo | `scraper.py` (`fecha_desde_url`, `fecha_desde_html`, `seccion_desde_url`) |
| R5 | Cadencia sub-diaria y corte temporal del agregado | Listo | Listo | `.github/workflows/scraping.yml`, `scripts/build_wordcloud_terms.py` |
| R6 | Agrupamiento de piezas por acontecimiento | — | Pendiente | Trabajo de análisis, no de pipeline |

### Qué hace ahora cada tirada

1. Recorre el listado **entero** de cada cabecera, sin cuota y sin caché. La
   cuota por medio (30/25/20) ha desaparecido de `config.py`; queda un tope de
   seguridad de 300 que solo salta si un selector se desmadra.
2. Registra **una observación por pieza y tirada**, esté o no en el corpus, con
   su posición dentro del listado de origen y la fuente. Es lo que mide
   duración de la atención y prominencia.
3. Da de alta las piezas nuevas **con tema o sin él**, sellándolas con la huella
   del clasificador y con la procedencia de su fecha.
4. Descarga el cuerpo solo de las piezas nuevas con tema, hasta **15 por
   cabecera y tirada**. Del mismo HTML sale la fecha exacta, así que no se paga
   dos veces.
5. Antes de empezar, pregunta al corpus remoto qué piezas ya conoce. Sin esa
   consulta, las cuatro tiradas diarias multiplicarían por cuatro las descargas,
   porque en integración continua la base local arranca vacía.

### Correcciones que salieron al verificar

- **Brotli anunciado sin soporte.** El cliente pedía `Accept-Encoding: br` sin
  tener la librería, así que ante una respuesta comprimida devolvía binario sin
  descomprimir, que pasaba el control de longitud mínima y se cacheaba como si
  fuera HTML. Una cabecera podía rendir cero por esto sin ningún error visible.
- **Listado servido desde una caché de siete días.** En integración continua no
  mordía porque el runner es efímero, pero en local habría fabricado permanencia
  falsa en la tabla de observaciones nada más crearla.
- **Enlaces de navegación en el denominador.** «Ver más» o «Sucesos» entran por
  el mismo selector CSS que las piezas. Antes daba igual, porque el clasificador
  los borraba; desde R1 contarían como denominador y deflactarían todas las
  cuotas. En la primera tirada real sobre El Hierro Hoy eran 6 de 43.
- **Colisión de nombres en el identificador de tirada.** El `run_id` de las
  observaciones se pisaba con el identificador de fila de `scraping_log`, de
  modo que cada cabecera creía estar en una tirada distinta y la permanencia
  quedaba inservible. Lo detectó una de las comprobaciones de `tests/`.
- **Filtrado de pendientes con 30.000 parámetros SQL.** La sincronización
  excluía lo ya subido con un `NOT IN` parametrizado; pasado el límite de
  variables de SQLite (32.766) habría reventado, y con el ritmo nuevo el corpus
  lo alcanza en semanas. Ahora se filtra en Python.

## 3 · Primera tirada real (verificación de campo)

Ejecutada contra El Hierro Hoy el 2026-09-10, con el pipeline nuevo:

| | |
|---|---|
| Piezas en el listado | 32 (antes la cuota la cortaba en 20) |
| Con tema | 9 |
| Sin tema (denominador) | 23, el 72 % |
| Observaciones | 32, posiciones 1–14 en el feed y 15–32 en la portada |
| Fecha real | 14 del feed, 3 del JSON-LD del artículo, 15 sintéticas declaradas |

El 72 % de denominador invisible confirma el orden de magnitud que anticipaba
el cuaderno: cualquier cuota calculada sobre el tramo antiguo está inflada por
un factor de esa escala.

## 4 · Auditoría del corpus

Consulta del apartado 4.3 del cuaderno, ejecutada el 2026-09-11, después del
sellado y antes de la primera tirada del régimen nuevo.

| Métrica | Valor |
|---|---|
| Piezas | 13.761 |
| Ventana | 2026-03-16 → 2026-09-10 |
| Tramo antiguo (`fecha_pub_origen IS NULL`) | 13.761 (100 %) |
| Sin sellar (`clasificador_version IS NULL`) | 0 |
| Piezas sin tema | 239 (1,7 %), todas del 16 al 19 de marzo |
| Fecha fiable (`fecha_pub_origen` no sintética) | 0 |
| Con `texto_full` | 10.639 (77,3 %) |
| Cabeceras con datos | 12 de las 14 configuradas entonces (hoy son 17) |
| Temas por pieza | 1,236 |
| Filas en `medios.observaciones` | 0 |
| Filas en `medios.wordcloud_terms` | 0 antes de la reconstrucción del 2026-09-11 (ver apartado 6) |

### Cobertura de texto completo por cabecera

Es el hallazgo que agrava la amenaza A7: la cobertura no es «parcial pero
homogénea», es **radicalmente desigual**. Comparar encuadres entre estas
cabeceras confunde el marco con la calidad de extracción.

| Cabecera | Piezas | % con texto | Sin tema |
|---|---|---|---|
| canarias7 | 2.134 | 95,4 | 61 |
| eldia | 1.620 | 96,9 | 31 |
| laprovincia | 1.611 | 96,9 | 31 |
| canariasahora | 1.561 | 99,9 | 0 |
| laopinion | 1.361 | **58,6** | 30 |
| diariodeavisos | 1.278 | 95,9 | 40 |
| atlanticohoy | 1.277 | 99,0 | 0 |
| lavozdefuerteventura | 796 | **4,0** | 0 |
| gomeraverde | 709 | **3,9** | 0 |
| eltime | 575 | **0,0** | 0 |
| lancelotdigital | 566 | 100,0 | 0 |
| elhierrohoy | 273 | **0,0** | 0 |

`elpueblocanario` y `canariasnoticias` siguen sin ninguna pieza. El universo
efectivo de esa auditoría es 12.

### Alta de EFE, Europa Press y RTVC (2026-09-11)

El cuaderno declaraba 17 cabeceras desde su primera edición, pero tres no
existían en `config.py`. Ya están, y con esto el universo declarado y el
configurado coinciden: **17**.

| Cabecera | Fuente | Piezas en la prueba | Con tema | Fecha real |
|---|---|---|---|---|
| Europa Press Canarias | RSS (canal 287) + portada | 20 | 10 | 9 del feed, 11 de la URL |
| EFE Canarias | Portada | 10 | 6 | 6 de la URL, 3 del artículo |
| RTVC | Portada | 50 | 14 | 28 de la URL, 3 del artículo |

Tres cosas que conviene saber antes de usarlas:

- **RTVC no entra por API, aunque el cuaderno lo diga.** Su WordPress expone
  `/wp-json/wp/v2/posts`, pero fuerza un solo post por petición e ignora la
  paginación: `per_page=100` devuelve uno, y `page=2` devuelve el mismo. Sacar
  cincuenta piezas costaría cincuenta peticiones. Entra por portada, como las
  demás, y por eso su `fuente` es `html` y no `api`. La restricción `CHECK` de
  `noticias.fuente` se queda como está.
- **RTVC escribe la fecha en palabras** dentro del slug
  (`…-11-septiembre-2026`). El extractor de R4 ya la lee, así que 28 de sus 50
  piezas tienen fecha real sin descargar nada. Las que no la llevan, sobre todo
  recetas y deportes, se quedan con marca sintética declarada.
- **Una agencia no es un diario.** EFE y Europa Press alimentan a las demás
  cabeceras, de modo que su agenda es un antecedente de la del resto, no un
  competidor. En la matriz de convergencia, una correlación alta con ellas
  significa otra cosa que una correlación alta con otro diario, y conviene
  decirlo al interpretarla.

### Lo que salió al ponerlas en producción (2026-09-11)

- **EFE se quedó a cero en la primera tirada completa.** Devolvió un `429 Too
  Many Requests` al runner de Actions, y el cliente no reintentaba ningún 4xx.
  Un 429 no dice «esto no existe», dice «vuelve más tarde», así que ahora 429 y
  503 se reintentan respetando la cabecera `Retry-After`, con un tope de 60
  segundos. Comprobado en vivo: en la tirada siguiente EFE volvió a recibir un
  429 a mitad de faena, esperó y recuperó la pieza.
- **El parámetro `medio` del workflow era decorativo:** `scheduler.py --run-now`
  lo ignoraba, de modo que no había manera de relanzar una sola cabecera.
  Ahora funciona, admite varias separadas por comas y una errata falla al
  instante en vez de perderse en el log.
- **El orden de los selectores de cuerpo estaba al revés.** La heurística
  empezaba por la etiqueta `<article>`, pero muchas plantillas envuelven en
  `<article>` también las tarjetas de portada y los directos. EFE no rendía
  cuerpo porque el suyo vive en un `post-content` de WordPress, y RTVC rendía el
  rótulo «En Directo | …» repetido en lugar del artículo. Ahora van primero los
  contenedores con nombre propio. Comprobado sobre piezas reales: para
  Canarias7, El Día, La Provincia y Atlántico Hoy el texto extraído es idéntico
  antes y después.

La secuela en los datos está resuelta: **las 14 piezas de RTVC que habían
guardado navegación se volvieron a descargar** el 2026-09-11 con el extractor
corregido, y ya tienen el cuerpo real, de 1.181 a 3.759 caracteres y 2.339 de
media. Ninguna conserva el rastro «En Directo |», y ninguna otra cabecera estaba
afectada.

El agregado léxico no arrastra ese ruido: se reconstruyó a las 13:57, antes de
que esas piezas entraran en el corpus. Lo que sí es que todavía no incluye las
840 piezas del régimen nuevo, y las incorporará en su reconstrucción diaria.

## 5 · Deriva del clasificador, y sellado del corpus

Medida en seco el 2026-09-10 y aplicada el 2026-09-11, con `es_core_news_md`
cargado, sobre las 13.761 piezas del corpus.
Clasificador: `v2-29e00cc2d46f-es_core_news_md`.

| | |
|---|---|
| Etiqueta idéntica | 13.496 (98,1 %) |
| Etiqueta distinta | 265 (1,9 %) |
| Cambian de temas | 121 |
| Se quedan sin tema | 95 |
| Ganan tema (estaban vacías) | 49 |

**La deriva no está repartida: está toda en los cuatro primeros días del
corpus.** Del 20 de marzo en adelante, el clasificador de hoy reproduce
exactamente las 13.139 etiquetas guardadas.

| Día | Piezas | Distintas | |
|---|---|---|---|
| 2026-03-16 | 348 | 164 | 47,1 % |
| 2026-03-17 | 55 | 31 | 56,4 % |
| 2026-03-18 | 92 | 68 | 73,9 % |
| 2026-03-19 | 127 | 2 | 1,6 % |
| desde 2026-03-20 | 13.139 | 0 | 0,0 % |

Dos conclusiones para la ficha técnica:

- **El instrumento no se ha movido desde el 20 de marzo de 2026.** Las series
  construidas sobre el corpus a partir de esa fecha son comparables entre sí sin
  reservas por este motivo. La ventana del 16 al 19 de marzo es la única que
  arrastra etiquetas de un clasificador anterior.
- **Las piezas con temas vacíos son todas de esa misma ventana**, no un
  denominador parcial de un régimen posterior. Eran 193 antes del sellado y son
  239 después. No sirven como denominador de nada.

### El sellado, aplicado el 2026-09-11

| | |
|---|---|
| Etiquetas reescritas | 265, todas del 16 al 19 de marzo |
| Piezas selladas | 13.761, ninguna queda con `clasificador_version` a NULL |
| Verificación | Las 13.761 etiquetas releídas coinciden con lo previsto: 0 discrepancias |

Las etiquetas anteriores de esas 265 piezas quedan en
[`sellado-2026-09-11-etiquetas-anteriores.json`](sellado-2026-09-11-etiquetas-anteriores.json),
que es lo que hace la operación reversible. Las otras 13.496 no se tocaron: el
clasificador de hoy reproduce su etiqueta exactamente.

Consecuencia para cualquier cifra ya publicada sobre la ventana del 16 al 19 de
marzo: cambia un poco. Economía gana 92 etiquetas en el corpus, y política y
medio ambiente pierden 37 y 33.

## 6 · El agregado léxico estaba vaciándose solo

La tabla no estaba «sin construir»: estaba **siendo vaciada todos los días**.

El job `Build Wordcloud Terms` corrió en verde hasta el 2026-09-06 y falló los
cuatro días siguientes con el mismo error de PostgREST:

```
42P10 there is no unique or exclusion constraint matching the ON CONFLICT specification
```

La tabla había ganado la columna `periodo` en su clave primaria (R5), y el
`on_conflict` del script seguía nombrando la clave de tres columnas. Como el
script **trunca la tabla antes de insertar**, cada ejecución diaria la dejaba a
cero y moría. Desde el 7 de septiembre, la nube de palabras del dashboard venía
cayendo a su cálculo de respaldo en cliente sobre titulares, que es peor: no
pondera el artículo completo.

El arreglo va en este mismo cambio, junto con el corte mensual. Reconstruido el
2026-09-11 desde Actions sobre la rama (run 79, en verde), con las 13.521 piezas
con tema que producen términos:

| Periodo | Filas | Ámbitos | Piezas |
|---|---|---|---|
| `__all__` | 14.076 | 202 | 13.522 |
| 2026-03 | 6.760 | 93 | 1.168 |
| 2026-04 | 8.942 | 122 | 2.674 |
| 2026-05 | 9.199 | 127 | 2.796 |
| 2026-06 | 9.352 | 132 | 2.824 |
| 2026-07 | 9.005 | 126 | 2.531 |
| 2026-08 | 4.390 | 61 | 609 |
| 2026-09 | 5.812 | 85 | 920 |
| **Total** | **67.536** | | |

Dos advertencias antes de usar estos cortes para una serie de atributos:

- **Los meses no son comparables en volumen.** Agosto tiene 609 piezas y junio
  2.824. Eso no mide la actividad de la prensa canaria: mide cuántas tiradas del
  scraper salieron bien ese mes. Comparar vocabulario entre meses sí vale;
  comparar cuántos términos tiene cada mes, no.
- **El umbral de ámbito sigue siendo laxo.** El pipeline conserva 80 términos
  por ámbito con que aparezcan en 2 documentos, y solo descarta los ámbitos
  mensuales por debajo de 5 piezas. Para análisis, el cuaderno recomienda
  filtrar por `n_noticias` por debajo de unas 30.

### El dashboard publicado necesita el filtro de periodo

Cualquier consulta al agregado tiene que filtrar por `periodo` desde ahora: sin
él, la misma palabra vuelve hasta nueve veces por ámbito, una por corte. La
consulta de `index.html` pedía solo por `scope_key`, y se ha corregido en esta
rama para que pida `periodo = '__all__'`.

**Resuelto el 2026-09-11:** esa línea se llevó a `main` por separado (commit
`8742e28`), sin arrastrar el resto de la rama, y Pages volvió a desplegar. El
efecto que tenía no era teórico. Reproduciendo la consulta anterior sobre la
tabla ya reconstruida:

| | |
|---|---|
| Ámbitos cuyo top 55 cuela filas de cortes mensuales | 96 de 202 |
| Filas intrusas en total | 357 |
| Peor caso (`medio:canarias7\|tema:diversidad`) | 16 de 55 palabras |

Eran casi la mitad de los ámbitos, y los peores los de medio × tema, que es
donde vive el segundo nivel de agenda. El acumulado global apenas se veía
afectado, porque sus puntuaciones son mucho mayores que las de cualquier mes.

Comprobado contra la API ya con el filtro: los dos peores ámbitos pasan de 16 y
15 términos repetidos en sus 55 palabras a ninguno.

## 7 · Qué queda por hacer

1. **Decidir sobre el user-agent** (amenaza A9): es una decisión editorial, no
   técnica, y el volumen de peticiones se ha multiplicado por cuatro.
2. **Diagnosticar o retirar las dos cabeceras muertas**, para que el universo
   declarado y el efectivo coincidan.
3. **Vigilar el crecimiento**: del orden de 1.500 filas diarias de noticias más
   las observaciones. Si la cuota de Supabase se agota, el pipeline falla en
   silencio, porque `scheduler.py` captura las excepciones sin propagarlas.

## 8 · Aviso de seguridad pendiente

El asesor de Supabase marca como crítico que `medios.frecuencias_lexicas`
tiene **Row Level Security deshabilitada**: cualquiera con la *anon* key
—que es pública, va incrustada en `index.html`— puede leer y escribir esa
tabla. Está a 0 filas, así que el riesgo actual es de escritura, no de fuga.

La remediación no debe aplicarse a ciegas: activar RLS sin políticas bloquea
todo acceso. Decisión del equipo, no automática.

```sql
ALTER TABLE "medios"."frecuencias_lexicas" ENABLE ROW LEVEL SECURITY;
```

## 9 · Cómo repetir esta verificación

```bash
python -m unittest discover -s tests -v      # el plano del código
```

El plano del corpus se comprueba con la consulta de auditoría del apartado 4.3
del cuaderno. Mientras devuelva `tramo_antiguo = piezas`, el régimen nuevo no ha
empezado; en cuanto empiece, toda serie que cruce esa fecha mide en parte el
cambio del instrumento.
