"""Proceso que queda corriendo (servicio `programador` de docker-compose) y sincroniza Connectly una vez al día."""
import logging
import time
from datetime import datetime, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from connectly import sincronizar

log = logging.getLogger(__name__)


def proxima(hora: str, ahora: datetime) -> datetime:
    h, m = (int(x) for x in hora.split(":"))
    objetivo = ahora.replace(hour=h, minute=m, second=0, microsecond=0)
    return objetivo if objetivo > ahora else objetivo + timedelta(days=1)


class Command(BaseCommand):
    help = "Sincroniza Connectly todos los días a la hora SINCRONIZAR_HORA (por defecto 07:00)."

    def add_arguments(self, parser):
        parser.add_argument("--al-iniciar", action="store_true", help="Sincroniza también apenas arranca.")

    def handle(self, *args, al_iniciar=False, **opciones):
        hora = settings.SINCRONIZAR_HORA
        log.info("Programador listo: sincroniza Connectly todos los días a las %s.", hora)
        if al_iniciar:
            self._correr()
        while True:
            siguiente = proxima(hora, datetime.now())
            log.info("Próxima sincronización: %s", siguiente)
            while datetime.now() < siguiente:
                time.sleep(min(60, max(1, (siguiente - datetime.now()).total_seconds())))
            self._correr()

    def _correr(self):
        close_old_connections()
        try:
            for s in sincronizar.todas("programada"):
                log.info("%s: %s (%s nuevos, %s actualizados) %s", s.cuenta.empresa, s.estado, s.nuevos,
                         s.actualizados, s.detalle)
        except Exception:  # noqa: BLE001 - el programador nunca debe caerse
            log.exception("La sincronización programada falló.")
        finally:
            close_old_connections()
