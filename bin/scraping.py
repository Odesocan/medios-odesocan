"""
scraping.py — Punto de entrada del pipeline diario completo.

Encadena las cuatro fases: raspado → clasificación → sync con Supabase →
regeneración del dashboard. Es lo que ejecuta `.github/workflows/scraping.yml`.

Dos modos:
  1. Ejecución única (la que usa GitHub Actions):
       python bin/scraping.py --run-now

  2. Modo daemon (desarrollo o VPS sin cron):
       python bin/scraping.py

  3. Modo cron (producción en Linux/macOS), añadiendo a `crontab -e`:
       0 10 * * * /usr/bin/python3 /ruta/medios-odesocan/bin/scraping.py --run-now >> /ruta/logs/cron.log 2>&1

CRON CHEATSHEET para este proyecto:
  Cada hora:             0 * * * *
  Cada 2 horas:          0 */2 * * *
  Cada 2h (7-23h):       0 7-23/2 * * *
  Cada día a las 6am:    0 6 * * *
  Cada día a las 10am:   0 10 * * *
  Lunes a viernes 7am:   0 7 * * 1-5
"""

import sys
from pathlib import Path

# Permite ejecutar este script desde cualquier directorio: añade la raíz del
# repositorio a sys.path para que `import observatorio` funcione sin instalar
# el paquete.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse
import logging
import time

import schedule

from observatorio.almacenamiento.postgres import (
    sincronizar,
    sincronizar_log,
    sincronizar_observaciones,
)
from observatorio.comun.registro import configurar_logging
from observatorio.recoleccion.orquestador import scrapear_todos

log = logging.getLogger("scheduler")

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
        observaciones = sincronizar_observaciones()
        log.info("✓ Supabase — %d insertadas / %d observaciones / %d errores",
                 stats["insertadas"], observaciones, stats["errores"])
    except Exception as e:
        log.error("✗ Error en sincronización Supabase: %s", e, exc_info=True)

    # Regenerar dashboard D3 con datos frescos.
    # `index.html` carga sus datos de Supabase desde el navegador, así que lo
    # habitual es que no haya nada que reescribir. Se registra el resultado real
    # para no dar por bueno un paso que no ha hecho nada.
    try:
        from observatorio.publicacion.dashboard import main as generar_dashboard
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

    # Programar una única ejecución diaria a las 10:00.
    schedule.every().day.at("10:00").do(job)
    log.info("Ejecución programada cada día a las 10:00")

    while True:
        schedule.run_pending()
        proxima = schedule.next_run()
        log.info("Próxima ejecución: %s", proxima)
        time.sleep(60)
