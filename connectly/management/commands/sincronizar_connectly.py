import json

from django.core.management.base import BaseCommand, CommandError

from connectly import sincronizar
from connectly.models import CuentaConnectly


class Command(BaseCommand):
    help = "Trae el último reporte de Connectly de cada cuenta activa y lo guarda sin duplicar."

    def add_arguments(self, parser):
        parser.add_argument("--probar", action="store_true",
                            help="Solo lectura: muestra qué reportes devuelve la API, sin guardar nada.")
        parser.add_argument("--empresa", help="Solo la cuenta de esta empresa.")

    def handle(self, *args, probar=False, empresa=None, **opciones):
        cuentas = CuentaConnectly.objects.select_related("empresa")
        cuentas = cuentas.filter(empresa__nombre__iexact=empresa) if empresa else cuentas.filter(activa=True)
        if not cuentas:
            raise CommandError("No hay cuentas de Connectly registradas (agrégalas en el admin: Cuentas de Connectly).")
        for c in cuentas:
            if probar:
                try:
                    r = sincronizar.probar(c)
                except Exception as e:  # noqa: BLE001 - se informa cualquier error en modo prueba
                    self.stderr.write(self.style.ERROR(f"{c.empresa}: {e}"))
                    continue
                self.stdout.write(self.style.SUCCESS(f"{c.empresa}: la API respondió."))
                self.stdout.write(json.dumps(r, ensure_ascii=False, indent=2, default=str))
                continue
            s = sincronizar.cuenta(c, origen="manual")
            estilo = self.style.SUCCESS if s.estado == "ok" else (
                self.style.WARNING if s.estado == "sin_novedad" else self.style.ERROR)
            self.stdout.write(estilo(f"{c.empresa}: {s.get_estado_display()} · {s.nuevos:,} nuevos, "
                                     f"{s.actualizados:,} actualizados · {s.detalle}"))
