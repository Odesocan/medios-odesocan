# Estado verificado de la instrumentación

**Última verificación:** 10 de septiembre de 2026
**Verificado contra:** árbol de trabajo de `medios-odesocan` (rama `claude/admiring-fermat-dv7g64`) y proyecto Supabase `bd_odesocan` (`kdpsjutsgvghdtzoskkg`).

Este documento acompaña a [`CUADERNO_METODOLOGICO.md`](CUADERNO_METODOLOGICO.md).
El cuaderno describe el instrumento previsto; esto describe el que hay.

## Diagnóstico en una frase

Los cinco cambios R1–R5 están **implementados en el código y presentes en el
esquema**, pero el tramo nuevo del corpus **no ha empezado**: las 13.761 piezas
acumuladas siguen siendo todas del régimen antiguo, y lo seguirán siendo hasta
la primera tirada del pipeline reinstrumentado.

## 1 · Los tres planos, por separado

| Plano | Estado |
|---|---|
| Esquema Supabase | Régimen nuevo. `noticias.seccion`, `noticias.clasificador_version`, `noticias.fecha_pub_origen`, `medios.observaciones` y `wordcloud_terms.periodo` existen, con sus comentarios de columna, sus índices y su restricción única `(url_hash, run_id)`. |
| Código del pipeline | Régimen nuevo. R1–R5 implementados y con comprobaciones automáticas en `tests/`. |
| Corpus | Régimen antiguo al 100 %. Ninguna pieza lleva todavía sello de clasificador, fecha real ni observación de portada. |

## 2 · Hoja de ruta

| | Cambio | Esquema | Código | Dónde |
|---|---|---|---|---|
| R1 | Conservar las piezas sin tema | Listo | Listo | `scraper.py` (`guardar_noticia`, bucle de `scrapear_medio`), `supabase_loader.py` |
| R2 | Registrar posición y permanencia en portada | Listo | Listo | `scraper.py` (`registrar_observacion`), `supabase_loader.py` (`sincronizar_observaciones`) |
| R3 | Versión del clasificador y reclasificación | Listo | Listo | `clasificador.py` (`version_clasificador`), `scripts/reclasificar.py` |
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

Consulta del apartado 4.3 del cuaderno, ejecutada el 2026-09-10, antes de la
primera tirada del régimen nuevo.

| Métrica | Valor |
|---|---|
| Piezas | 13.761 |
| Ventana | 2026-03-16 → 2026-09-10 |
| Tramo antiguo (`clasificador_version IS NULL`) | 13.761 (100 %) |
| Piezas sin tema | 193 (1,4 %) |
| Fecha fiable (`fecha_pub_origen` no sintética) | 0 |
| Con `texto_full` | 10.639 (77,3 %) |
| Cabeceras con datos | 12 de 14 configuradas |
| Temas por pieza | 1,24 |
| Filas en `medios.observaciones` | 0 |
| Filas en `medios.wordcloud_terms` | 0 |

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

`elpueblocanario` y `canariasnoticias` siguen sin ninguna pieza: el universo
efectivo es 12, no 15 ni 17. El cuaderno declara 17 cabeceras, dos agencias y
RTVC; `config.py` tiene 14 y ninguna fuente de tipo API. Además,
`noticias.fuente` tiene un `CHECK` que solo admite `'rss'` y `'html'`: añadir
una API exige tocar la restricción.

## 5 · Qué queda por hacer

1. **Sellar el corpus histórico** con `scripts/reclasificar.py`. Su modo en seco
   mide antes cuánta deriva hay, que es una cifra publicable por sí misma.
   Requiere el modelo de spaCy: sin vectores el clasificador etiqueta distinto.
2. **Reconstruir el agregado léxico**, hoy a cero filas, para que el segundo
   nivel de agenda vuelva a ser calculable y estrene el corte mensual.
3. **Decidir sobre el user-agent** (amenaza A9): es una decisión editorial, no
   técnica, y el volumen de peticiones se ha multiplicado por cuatro.
4. **Diagnosticar o retirar las dos cabeceras muertas**, para que el universo
   declarado y el efectivo coincidan.
5. **Vigilar el crecimiento**: del orden de 1.500 filas diarias de noticias más
   las observaciones. Si la cuota de Supabase se agota, el pipeline falla en
   silencio, porque `scheduler.py` captura las excepciones sin propagarlas.

## 6 · Aviso de seguridad pendiente

El asesor de Supabase marca como crítico que `medios.frecuencias_lexicas`
tiene **Row Level Security deshabilitada**: cualquiera con la *anon* key
—que es pública, va incrustada en `index.html`— puede leer y escribir esa
tabla. Está a 0 filas, así que el riesgo actual es de escritura, no de fuga.

La remediación no debe aplicarse a ciegas: activar RLS sin políticas bloquea
todo acceso. Decisión del equipo, no automática.

```sql
ALTER TABLE "medios"."frecuencias_lexicas" ENABLE ROW LEVEL SECURITY;
```

## 7 · Cómo repetir esta verificación

```bash
python -m unittest discover -s tests -v      # el plano del código
```

El plano del corpus se comprueba con la consulta de auditoría del apartado 4.3
del cuaderno. Mientras devuelva `tramo_antiguo = piezas`, el régimen nuevo no ha
empezado; en cuanto empiece, toda serie que cruce esa fecha mide en parte el
cambio del instrumento.
