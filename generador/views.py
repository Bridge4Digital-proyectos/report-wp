"""Generador de reportes HTML: elige una campaña guardada o sube un CSV/Excel y descarga un HTML con la marca."""
import re
import uuid
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string

from generador import servicios
from nucleo.models import Empresa
from nucleo.servicios import datos
from nucleo.servicios.marca import para_cliente

SESION = "generador_archivo"


def _carpeta() -> Path:
    c = Path(settings.BASE_DIR) / "data" / "subidas"
    c.mkdir(parents=True, exist_ok=True)
    return c


def _campanas(df):
    if df.empty:
        return []
    t = df.groupby("difusion").agg(mensajes=("difusion", "size"), inicio=("despachado_en", "min"))
    t = t.sort_values("inicio", ascending=False)
    return [{"difusion": d, "mensajes": f"{int(r.mensajes):,}", "inicio": r.inicio} for d, r in t.iterrows()]


def inicio(request):
    todo = datos.mensajes()
    empresas = sorted(todo["empresa"].unique()) if not todo.empty else []
    empresa = request.GET.get("empresa") or request.session.get("empresa")
    if empresa not in empresas:
        empresa = empresas[0] if empresas else None
    plataformas = sorted(todo[todo["empresa"] == empresa]["plataforma"].unique()) if empresa else []
    plataforma = request.GET.get("plataforma")
    if plataforma not in plataformas:
        plataforma = plataformas[0] if plataformas else None
    df = todo[(todo["empresa"] == empresa) & (todo["plataforma"] == plataforma)] if empresa else todo.iloc[0:0]

    if request.method == "POST":
        archivo = request.FILES.get("archivo")
        if not archivo:
            messages.error(request, "Elige un archivo CSV o Excel.")
            return redirect("generador:inicio")
        ruta = _carpeta() / f"generador_{uuid.uuid4().hex}{Path(archivo.name).suffix.lower()}"
        with ruta.open("wb") as f:
            for parte in archivo.chunks():
                f.write(parte)
        try:
            servicios.leer_archivo(str(ruta), archivo.name)
        except ValueError as e:
            ruta.unlink(missing_ok=True)
            messages.error(request, str(e))
            return redirect("generador:inicio")
        anterior = request.session.get(SESION)
        if anterior:
            Path(anterior["ruta"]).unlink(missing_ok=True)
        request.session[SESION] = {"ruta": str(ruta), "nombre": archivo.name,
                                   "empresa": request.POST.get("empresa_archivo") or ""}
        return redirect(f"{request.path}#archivo")

    sesion = request.session.get(SESION)
    del_archivo = None
    if sesion and Path(sesion["ruta"]).exists():
        plataforma_archivo, df_archivo = servicios.mensajes_de_archivo(sesion["ruta"], sesion["nombre"],
                                                                       sesion["empresa"] or "—")
        del_archivo = {"nombre": sesion["nombre"], "plataforma": plataforma_archivo, "empresa": sesion["empresa"],
                       "mensajes": f"{len(df_archivo):,}", "campanas": _campanas(df_archivo)}
    elif sesion:
        request.session.pop(SESION, None)

    return render(request, "generador/inicio.html", {
        "titulo": "Reporte HTML", "empresas": empresas, "empresa": empresa, "plataformas": plataformas,
        "plataforma": plataforma, "campanas": _campanas(df), "archivo": del_archivo,
        "todas_empresas": list(Empresa.objects.values_list("nombre", flat=True)),
    })


def quitar_archivo(request):
    sesion = request.session.pop(SESION, None)
    if sesion:
        Path(sesion["ruta"]).unlink(missing_ok=True)
    return redirect("generador:inicio")


def _nombre_archivo(texto: str) -> str:
    limpio = re.sub(r"[^\w\-]+", "_", texto, flags=re.UNICODE).strip("_")
    return limpio[:80] or "campana"


def reporte(request):
    """El reporte HTML (en el navegador o como descarga con ?descargar=1)."""
    g = request.GET
    campana = g.get("campana", "")
    if g.get("origen") == "archivo":
        sesion = request.session.get(SESION)
        if not sesion or not Path(sesion["ruta"]).exists():
            raise Http404("El archivo ya no está disponible: vuelve a subirlo.")
        _, df = servicios.mensajes_de_archivo(sesion["ruta"], sesion["nombre"], sesion["empresa"] or "—")
        origen = f"Archivo: {sesion['nombre']}"
    else:
        todo = datos.mensajes()
        df = todo[(todo["empresa"] == g.get("empresa")) & (todo["plataforma"] == g.get("plataforma"))]
        origen = "Base de datos de la app"
    df = df[df["difusion"] == campana]
    if df.empty:
        raise Http404("No se encontró la campaña.")
    # Desde el formulario llega "opciones"; un enlace directo sin opciones incluye las respuestas.
    con_respuestas = g.get("respuestas") == "1" if g.get("opciones") else True
    # El reporte lo recibe la empresa: nunca lleva costos.
    ctx = servicios.calcular(df, datos.significados(), respuestas_cliente=con_respuestas)
    ctx.update({"origen": para_cliente(origen), "plataforma": para_cliente(ctx["plataforma"]), "logo": servicios.logo("logo_horizontal.png"),
                "logo_blanco": servicios.logo("logo_horizontal_blanco.png"), "icono": servicios.logo("icono.png"),
                "fuentes": servicios.fuentes_css()})
    html = render_to_string("generador/reporte.html", ctx)
    resp = HttpResponse(html, content_type="text/html; charset=utf-8")
    if g.get("descargar"):
        nombre = f"Reporte_{_nombre_archivo(campana)}_{ctx['generado']:%Y%m%d}.html"
        resp["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return resp

