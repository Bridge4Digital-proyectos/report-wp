from django.contrib import admin

from nucleo.models import Campana, Carga, Empresa, Significado, Tarifa


@admin.register(Empresa)
class EmpresaAdmin(admin.ModelAdmin):
    search_fields = ["nombre"]


@admin.register(Campana)
class CampanaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "empresa", "plataforma", "categoria", "solicitado_por", "fecha_solicitud"]
    list_filter = ["empresa", "plataforma", "categoria"]
    search_fields = ["nombre"]
    list_editable = ["categoria"]


@admin.register(Carga)
class CargaAdmin(admin.ModelAdmin):
    list_display = ["fecha_carga", "empresa", "plataforma", "origen", "archivo", "filas_nuevas", "filas_actualizadas",
                    "filas_duplicadas", "usuario"]
    list_filter = ["empresa", "plataforma", "origen"]


@admin.register(Significado)
class SignificadoAdmin(admin.ModelAdmin):
    list_display = ["empresa", "difusion", "valor", "significado", "sentido"]
    list_filter = ["empresa", "sentido"]


@admin.register(Tarifa)
class TarifaAdmin(admin.ModelAdmin):
    list_display = ["empresa", "categoria", "precio", "moneda", "actualizado"]
    list_filter = ["empresa", "categoria"]
