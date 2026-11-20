"""Respaldo completo de los datos (JSON comprimido de Django): sirve igual con SQLite o PostgreSQL."""
import gzip
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command

APPS = ["auth.user", "nucleo", "connectly"]


def respaldar(motivo: str = "manual") -> Path:
    carpeta = Path(settings.CARPETA_RESPALDOS)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"respaldo_{motivo}_{datetime.now():%Y%m%d_%H%M%S}.json.gz"
    with gzip.open(destino, "wt", encoding="utf-8") as f:
        call_command("dumpdata", *APPS, stdout=f, natural_foreign=True)
    return destino
