"""Datos comunes a todas las plataformas: empresas, campañas, mensajes, historial de cargas y significados."""
import time

from django.db import models

PLATAFORMAS = [("Connectly", "Connectly")]
CATEGORIAS = [("UTILITY", "UTILITY"), ("MARKETING", "MARKETING")]
# Variantes de Meta que en Connectly cuentan como la misma categoría.
EQUIVALENCIAS = {"MARKETING_LITE": "MARKETING"}


def categoria_normal(valor) -> str:
    c = str(valor or "UTILITY").strip().upper()
    return EQUIVALENCIAS.get(c, c)
SENTIDOS = [("Positiva", "Positiva"), ("Neutral", "Neutral"), ("Negativa", "Negativa")]


class Empresa(models.Model):
    nombre = models.CharField(max_length=200, unique=True)

    class Meta:
        ordering = ["nombre"]

    def __str__(self):
        return self.nombre


class Campana(models.Model):
    """Un envío (lote o prueba) de una difusión; las campañas completas se agrupan al analizar."""
    plataforma = models.CharField(max_length=20, choices=PLATAFORMAS)
    nombre = models.CharField(max_length=500)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="campanas")
    categoria = models.CharField("categoría Meta", max_length=20, choices=CATEGORIAS, default="UTILITY")
    solicitado_por = models.CharField(max_length=200, blank=True, null=True)
    fecha_solicitud = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = "envío de campaña"
        verbose_name_plural = "envíos de campañas"
        constraints = [models.UniqueConstraint(fields=["plataforma", "nombre", "empresa"], name="campana_unica")]

    def __str__(self):
        return self.nombre

    def save(self, *args, **kwargs):
        self.categoria = categoria_normal(self.categoria)
        super().save(*args, **kwargs)


class Mensaje(models.Model):
    campana = models.ForeignKey(Campana, on_delete=models.CASCADE, related_name="mensajes")
    telefono = models.CharField(max_length=40, blank=True, null=True)
    session_id = models.CharField(max_length=200)
    despachado_en = models.DateTimeField(blank=True, null=True)
    enviado_en = models.DateTimeField(blank=True, null=True)
    entregado_en = models.DateTimeField(blank=True, null=True)
    leido_en = models.DateTimeField(blank=True, null=True)
    opt_out_en = models.DateTimeField(blank=True, null=True)
    error_code = models.CharField(max_length=60, blank=True, null=True)
    error_msg = models.TextField(blank=True, null=True)
    estado = models.CharField(max_length=20)
    respuesta = models.TextField(blank=True, default="")
    clics_boton = models.IntegerField(default=0)
    clics_link = models.IntegerField(default=0)
    plantilla = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["campana", "session_id"], name="mensaje_unico")]


class Carga(models.Model):
    ORIGENES = [("manual", "Archivo subido"), ("api", "API de Connectly"), ("migracion", "App anterior")]
    archivo = models.CharField(max_length=300, blank=True)
    plataforma = models.CharField(max_length=20, choices=PLATAFORMAS)
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="cargas")
    fecha_carga = models.DateTimeField()
    origen = models.CharField(max_length=20, choices=ORIGENES, default="manual")
    filas_nuevas = models.IntegerField(default=0)
    filas_actualizadas = models.IntegerField(default=0)
    filas_duplicadas = models.IntegerField("sin cambios", default=0)
    usuario = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ["-id"]


class Significado(models.Model):
    """Qué significa cada valor de respuesta en UNA campaña y si es positiva, neutral o negativa."""
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="significados")
    difusion = models.CharField(max_length=500)  # nombre de campaña normalizado
    valor = models.CharField(max_length=300)
    significado = models.CharField(max_length=300, blank=True)
    sentido = models.CharField(max_length=20, choices=SENTIDOS)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["empresa", "difusion", "valor"], name="significado_unico")]


class Version(models.Model):
    """Contador que sube con cada cambio de datos: invalida la caché en todos los procesos del servidor."""
    valor = models.BigIntegerField(default=0)

    @classmethod
    def actual(cls) -> int:
        v = cls.objects.filter(pk=1).values_list("valor", flat=True).first()
        return v or 0

    @classmethod
    def subir(cls):
        # Marca de tiempo en nanosegundos: nunca se repite, ni siquiera si una transacción se revierte.
        valor = time.time_ns()
        if not cls.objects.filter(pk=1).update(valor=valor):
            cls.objects.create(pk=1, valor=valor)


class Tarifa(models.Model):
    """Precio que Bridge4 cobra a cada empresa por mensaje entregado de cada categoría de Meta.

    En el Dashboard (interno) da los ingresos de Bridge4; en lo que recibe la empresa, su costo."""
    MONEDAS = [("USD", "USD"), ("BOB", "Bs")]
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="tarifas")
    categoria = models.CharField("categoría Meta", max_length=20, choices=CATEGORIAS)
    precio = models.DecimalField("precio por mensaje entregado", max_digits=10, decimal_places=5)
    moneda = models.CharField(max_length=3, choices=MONEDAS, default="USD")
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["empresa__nombre", "categoria"]
        constraints = [models.UniqueConstraint(fields=["empresa", "categoria"], name="tarifa_unica")]

    def __str__(self):
        return f"{self.empresa} · {self.categoria}: {self.precio} {self.moneda}"
