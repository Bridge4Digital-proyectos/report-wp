from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from connectly import importador, sincronizar
from connectly.models import CuentaConnectly, Sincronizacion
from nucleo.views.carga import flujo


def inicio(request):
    cuentas = CuentaConnectly.objects.select_related("empresa")
    filas = [{"cuenta": c, "ultima": c.sincronizaciones.first(), "en_curso": sincronizar.en_curso(c),
              "ultima_ok": c.sincronizaciones.filter(estado="ok").first()} for c in cuentas]
    return render(request, "connectly/inicio.html", {
        "titulo": "Connectly", "cuentas": filas, "alguna_en_curso": any(f["en_curso"] for f in filas),
        "registro": Sincronizacion.objects.select_related("cuenta__empresa")[:30]})


@require_POST
def sincronizar_ahora(request):
    cuentas = CuentaConnectly.objects.filter(activa=True).select_related("empresa")
    if request.POST.get("cuenta"):
        cuentas = CuentaConnectly.objects.filter(pk=request.POST["cuenta"]).select_related("empresa")
    cuentas = [c for c in cuentas if not sincronizar.en_curso(c)]
    if not cuentas:
        messages.warning(request, "No hay cuentas para sincronizar (o ya hay una sincronización en curso).")
    else:
        sincronizar.en_segundo_plano(cuentas, "manual")
        messages.info(request, "Sincronización iniciada. El reporte de 30 días tarda unos minutos; esta página se "
                               "actualiza sola hasta que termine.")
    return redirect("connectly:inicio")


def cargar(request):
    return flujo(request, plataforma="Connectly", importador=importador, plantilla="nucleo/cargar.html",
                 extensiones=".csv", ayuda="Sube el CSV de difusiones exportado desde Connectly (Analytics → Download "
                                           "CSV). Úsalo solo si la sincronización automática no trae algún reporte.")
