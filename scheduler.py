"""
scheduler.py — Ejecuta scraping + sync de forma periódica, sin iniciar el dashboard.

Dos modos:
  1. Modo daemon (recomendado para desarrollo/VPS sin cron):
       python scheduler.py

  2. Modo cron (recomendado para producción en Linux/macOS):
       Añade a crontab:  crontab -e
       # Cada seis horas, como el workflow de Actions
       0 2,8,14,20 * * * /usr/bin/python3 /ruta/canarias_monitor/scheduler.py >> /ruta/logs/cron.log 2>&1

La cadencia de referencia son cuatro tiradas diarias, cada seis horas (R5):
es lo que da grano intradiario a la permanencia en portada y deja ver las
piezas que aparecen y desaparecen dentro del mismo ciclo. Cambiarla cambia el
significado de la columna `observaciones`, así que no es un ajuste inocuo:
cualquier serie que use permanencia debe declarar cuántas tiradas diarias
había en el periodo analizado.

CRON CHEATSHEET para este proyecto:
  Cada seis horas:       0 2,8,14,20 * * *
  Cada hora:             0 * * * *
  Cada 2 horas:          0 */2 * * *
  Cada día a las 6am:    0 6 * * *
  Lunes a viernes 7am:   0 7 * * 1-5
"""

import argparse
import logging
import time

import schedule

from scraper import scrapear_todos
from supabase_loader import sincronizar, sincronizar_log, sincronizar_observaciones

log = logging.getLogger("scheduler")

# Las mismas cuatro horas que `.github/workflows/scraping.yml`. En UTC, como el
# cron de Actions.
HORAS_DE_TIRADA = ("02:00", "08:00", "14:00", "20:00")


def configurar_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def job() -> None:
    configurar_logging()
    log.info("▶ Ejecutando scraping programado…")
    try:
        resultados = scrapear_todos(dry_run=False, extraer_articulos=True)
        nuevas = sum(r.get("nuevas", 0) for r in resultados)
        log.info("✓ Scraping completado — %d noticias nuevas", nuevas)
    except Exception as e:
        log.error("✗ Error en scraping programado: %s", e, exc_info=True)
        return   # No intentar sync si el scraping falló

    # Sincronizar con Supabase tras cada scraping
    try:
        log.info("▶ Sincronizando con Supabase…")
        stats = sincronizar()
        sincronizar_log(resultados)
        log.info(
            "✓ Supabase — %d insertadas (%d sin tema) / %d errores",
            stats["insertadas"], stats.get("sin_tema", 0), stats["errores"],
        )
    except Exception as e:
        log.error("✗ Error en sincronización Supabase: %s", e, exc_info=True)

    # Las observaciones van aparte: miden permanencia en portada, no altas, y
    # se escriben aunque no haya entrado ninguna pieza nueva (R2).
    try:
        stats_obs = sincronizar_observaciones()
        log.info(
            "✓ Observaciones — %d insertadas de %d locales",
            stats_obs["insertadas"], stats_obs["locales"],
        )
    except Exception as e:
        log.error("✗ Error sincronizando observaciones: %s", e, exc_info=True)

    # Regenerar dashboard D3 con datos frescos.
    # `index.html` carga sus datos de Supabase desde el navegador, así que lo
    # habitual es que no haya nada que reescribir. Se registra el resultado real
    # para no dar por bueno un paso que no ha hecho nada.
    try:
        from generate_dashboard import main as generar_dashboard
        if generar_dashboard():
            log.info("✓ Dashboard D3 regenerado")
        else:
            log.info("• Dashboard D3 sin cambios (index.html se sirve desde Supabase)")
    except Exception as e:
        log.error("✗ Error regenerando dashboard D3: %s", e, exc_info=True)


if __name__ == "__main__":
    configurar_logging()
    parser = argparse.ArgumentParser(description="Scheduler del monitor de medios")
    parser.add_argument(
        "--run-now",
        action="store_true",
        help="Ejecuta scraping + sync inmediatamente y termina",
    )
    args = parser.parse_args()

    if args.run_now:
        log.info("Ejecución manual inmediata del scheduler")
        job()
        raise SystemExit(0)

    log.info("Scheduler iniciado en modo headless. No lanza el dashboard. Ctrl+C para detener.")

    # Cuatro tiradas diarias, cada seis horas, igual que el workflow de Actions
    # (R5). El modo daemon y el cron tienen que coincidir: si no, la columna
    # `observaciones` mediría permanencias con granos distintos según quién
    # ejecutase el pipeline.
    for hora in HORAS_DE_TIRADA:
        schedule.every().day.at(hora).do(job)
    log.info("Ejecuciones programadas: %s", ", ".join(HORAS_DE_TIRADA))

    while True:
        schedule.run_pending()
        proxima = schedule.next_run()
        log.info("Próxima ejecución: %s", proxima)
        time.sleep(60)
