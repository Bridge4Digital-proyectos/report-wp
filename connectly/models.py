"""Cuentas de Connectly (una por empresa) y el registro de cada sincronización con la API."""
import os

from django.db import models

from nucleo.models import Empresa


class CuentaConnectly(models.Model):
    empresa = models.OneToOneField(Empresa, on_delete=models.CASCADE, related_name="cuenta_connectly")
    business_id = models.CharField("Business ID", max_length=100)
    variable_api_key = models.CharField(
        "variable con la API key", max_length=100, default="CONNECTLY_API_KEY",
        help_text="Nombre de la variable del archivo .env que tiene la API key (la clave nunca se guarda aquí).")
    nombre_reporte = models.CharField(
        "nombre del reporte", max_length=200, default="Campaign_Report_-_Ultimos_30_dias_diario", blank=True,
        help_text="Comienzo del nombre del reporte programado de Connectly que se importa (se toma el más reciente). "
                  "Vacío = cualquier reporte del tipo indicado.")
    tipo_reporte = models.CharField(max_length=100, default="campaign.sessions.v1", blank=True,
                                    help_text="Tipo de reporte de la API (campaign.sessions.v1 en las cuentas de Tigo).")
    activa = models.BooleanField(default=True, help_text="Solo las cuentas activas se sincronizan cada día.")

    class Meta:
        verbose_name = "cuenta de Connectly"
        verbose_name_plural = "cuentas de Connectly"

    def __str__(self):
        return f"{self.empresa} ({self.business_id})"

    def api_key(self) -> str:
        clave = os.environ.get(self.variable_api_key, "").strip()
        if not clave:
            raise ValueError(f"Falta la variable {self.variable_api_key} en el archivo .env con la API key de "
                             f"Connectly de {self.empresa}.")
        return clave

    @property
    def tiene_clave(self) -> bool:
        return bool(os.environ.get(self.variable_api_key, "").strip())


class Sincronizacion(models.Model):
    ESTADOS = [("en_curso", "En curso"), ("ok", "Correcta"), ("sin_novedad", "Sin reporte nuevo"), ("error", "Error")]
    cuenta = models.ForeignKey(CuentaConnectly, on_delete=models.CASCADE, related_name="sincronizaciones")
    inicio = models.DateTimeField()
    fin = models.DateTimeField(null=True, blank=True)
    estado = models.CharField(max_length=20, choices=ESTADOS)
    run_id = models.CharField("ejecución del reporte", max_length=200, blank=True)
    reporte_creado = models.DateTimeField(null=True, blank=True)
    nuevos = models.IntegerField(default=0)
    actualizados = models.IntegerField(default=0)
    sin_cambios = models.IntegerField(default=0)
    detalle = models.TextField(blank=True)
    origen = models.CharField(max_length=20, default="programada")  # programada / manual

    class Meta:
        ordering = ["-inicio"]
        verbose_name = "sincronización"
        verbose_name_plural = "sincronizaciones"
