from django.core.management.base import BaseCommand

from nucleo.servicios.respaldo import respaldar


class Command(BaseCommand):
    help = "Guarda un respaldo completo de los datos en la carpeta de respaldos (JSON comprimido)."

    def handle(self, *args, **opciones):
        self.stdout.write(self.style.SUCCESS(f"Respaldo guardado en {respaldar()}"))
