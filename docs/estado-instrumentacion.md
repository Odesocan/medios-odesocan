# Estado verificado de la instrumentación

**Fecha de verificación:** 10 de septiembre de 2026
**Verificado contra:** árbol de trabajo de `medios-odesocan` (rama `claude/admiring-fermat-dv7g64`, idéntica a `main`) y proyecto Supabase `bd_odesocan` (`kdpsjutsgvghdtzoskkg`).

Este documento acompaña a [`CUADERNO_METODOLOGICO.md`](CUADERNO_METODOLOGICO.md).
El cuaderno describe el instrumento previsto; esto describe el que hay.

## Diagnóstico en una frase

El **esquema** de la base de datos ya es el de la segunda edición, pero el
**código** del pipeline sigue siendo el de la primera, así que el tramo nuevo
del corpus **no ha empezado**: las columnas y tablas nuevas existen y están
vacías, y las 13.761 piezas acumuladas pertenecen todas al tramo antiguo.

## 1 · Los tres planos, por separado

| Plano | Estado |
|---|---|
| Esquema Supabase | Segunda edición. `noticias.seccion`, `noticias.clasificador_version`, `noticias.fecha_pub_origen`, `medios.observaciones` y `wordcloud_terms.periodo` existen, con sus comentarios de columna. |
| Código del pipeline | Primera edición. Ninguno de los cinco cambios R1–R5 está implementado. |
| Corpus | Primera edición al 100 %. Ninguna pieza lleva sello de clasificador, fecha real ni observación de portada. |

## 2 · Hoja de ruta: cuaderno frente a código

| | Cambio | Cuaderno | Esquema | Código | Evidencia en el código |
|---|---|---|---|---|---|
| R1 | Conservar las piezas sin tema | Aplicado | Listo | **No** | `scraper.py:806` descarta (`if not temas: continue`); `supabase_loader.py:131` purga las que queden |
| R2 | Registrar la posición en portada | Aplicado | Listo (`observaciones`) | **No** | No hay ninguna escritura en `medios.observaciones` ni variable `posicion` en todo el repositorio |
| R3 | Versión del clasificador y reclasificación | Aplicado | Listo (columna) | **No** | `clasificador.py` no emite huella; el cargador no escribe `clasificador_version` |
| R4 | Fecha de publicación real y su procedencia | Aplicado | Listo (columna) | **No** | No existe extracción de fecha desde URL, JSON-LD, `<meta>` o `<time>`; `fecha_pub_origen` nunca se escribe |
| R5 | Cadencia sub-diaria y corte temporal del agregado | Aplicado | Listo (`periodo`) | **No** | `.github/workflows/scraping.yml:13` → `cron: "0 10 * * *"` (una tirada diaria); `scripts/build_wordcloud_terms.py:374` trunca la tabla entera y no escribe `periodo` |
| R6 | Agrupamiento por acontecimiento | Pendiente | — | — | Trabajo de análisis, no de pipeline |

### Otras divergencias entre el cuaderno y el código

| Afirmación del cuaderno | Realidad del repositorio |
|---|---|
| 17 cabeceras configuradas, dos agencias y RTVC | 14 en `config.py`. No hay EFE, Europa Press ni RTVC |
| Fuente API REST para RTVC | No existe. Además `noticias.fuente` tiene un `CHECK` que solo admite `'rss'` y `'html'`: añadir una API exige tocar la restricción |
| Cuota del listado sin tope | `max_items` sigue en 30 / 25 / 20 por cabecera (`config.py`), con techo global de 50 (`config.py:644`) |
| Cuota de texto completo: 15 artículos por cabecera y tirada | No hay tal presupuesto: se intenta la descarga de toda pieza nueva con tema (`scraper.py:815`) |
| Ficheros `observatorio/`, `db/esquema.sql`, `ARQUITECTURA.md` | No existen. El repositorio es plano: `scraper.py`, `clasificador.py`, `supabase_loader.py`, `scheduler.py`, `generate_dashboard.py` |

### Lo que el cuaderno describe bien

Comprobado y correcto: 15 temas; umbral `SCORE_MINIMO = 2.6` (`clasificador.py:29`);
`peso_titulo` a 4 en violencia de género y salud mental y a 2 en política y medio
ambiente; truncamiento de `texto_full` a 5.000 caracteres; `respetar_robots = False`
(`config.py:649`) y rotación de 12 user-agents de navegador (amenaza A9).

## 3 · Auditoría del corpus

Consulta del apartado 4.3 del cuaderno, ejecutada el 2026-09-10.

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
cabeceras hoy confunde el marco con la calidad de extracción.

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
efectivo es 12, no 15 ni 17.

Ninguna cabecera registra `seccion` (0 valores distintos en las doce).

## 4 · Consecuencias para el análisis, hoy

1. **Toda cuota calculada ahora es relativa a la agenda de ODESOCAN**, no a la
   producción del medio. Las 193 piezas sin tema no son un denominador: son un
   residuo, y no cubren a todas las cabeceras.
2. **No hay prominencia ni duración de la atención.** `observaciones` está
   vacía, así que las filas 4 y 5 de la Tabla 3 del cuaderno son «bloqueado»,
   no «disponible».
3. **No hay análisis temporal por fecha de publicación.** Cero piezas con fecha
   fiable: la única marca es `fecha_scrap`, que codifica el orden del
   diccionario de configuración, no el de publicación. La trampa del capítulo 8
   sigue activa, no evitable.
4. **El segundo nivel de agenda no es calculable ahora mismo**, no por diseño
   sino porque el agregado está vacío. Hay que reconstruirlo antes de usarlo.
5. **El encuadre está limitado a las siete cabeceras con cobertura de texto
   alta.** Las otras cinco no tienen cuerpo que codificar.

## 5 · Aviso de seguridad pendiente

El asesor de Supabase marca como crítico que `medios.frecuencias_lexicas`
tiene **Row Level Security deshabilitada**: cualquiera con la *anon* key
—que es pública, va incrustada en `index.html`— puede leer y escribir esa
tabla. Está a 0 filas, así que el riesgo actual es de escritura, no de fuga.

La remediación no debe aplicarse a ciegas: activar RLS sin políticas bloquea
todo acceso. Decisión del equipo, no automática.

```sql
ALTER TABLE "medios"."frecuencias_lexicas" ENABLE ROW LEVEL SECURITY;
```

## 6 · Cómo repetir esta verificación

```bash
# Plano código
grep -rn "observaciones\|fecha_pub_origen\|clasificador_version\|posicion\|periodo" \
     --include=*.py --include=*.sql --include=*.yml .
grep -n "cron" .github/workflows/scraping.yml
```

El plano corpus se comprueba con la consulta de auditoría del apartado 4.3 del
cuaderno. Mientras devuelva `tramo_antiguo = piezas`, el régimen nuevo no ha
empezado.
