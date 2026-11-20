from django.contrib import admin

from connectly.models import CuentaConnectly, Sincronizacion


@admin.register(CuentaConnectly)
class CuentaConnectlyAdmin(admin.ModelAdmin):
    list_display = ["empresa", "nombre_reporte", "tipo_reporte", "variable_api_key", "activa", "clave_cargada"]

    @admin.display(boolean=True, description="API key en .env")
    def clave_cargada(self, obj):
        return obj.tiene_clave


@admin.register(Sincronizacion)
class SincronizacionAdmin(admin.ModelAdmin):
    list_display = ["inicio", "cuenta", "origen", "estado", "nuevos", "actualizados", "detalle"]
    list_filter = ["estado", "cuenta"]
