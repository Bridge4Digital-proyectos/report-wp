"""Subir un reporte a mano (lo usa la app connectly): subir -> revisar campañas -> guardar."""
import uuid
from datetime import date
from io import BytesIO
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from nucleo.models import Campana, Empresa
from nucleo.presentacion import tabla
from nucleo.servicios import analisis, cargas, datos

NUEVA = "__nueva__"


def _carpeta() -> Path:
    c = Path(settings.BASE_DIR) / "data" / "subidas"
    c.mkdir(parents=True, exist_ok=True)
    return c


def _leer(sesion, importador):
    contenido = BytesIO(Path(sesion["ruta"]).read_bytes())
    contenido.name = sesion["nombre"]  # el importador decide CSV/Excel por la extensión
    return importador.parse(contenido)


def flujo(request, *, plataforma: str, importador, plantilla: str, extensiones: str, ayuda: str):
    clave = f"subida_{plataforma}"
    sesion = request.session.get(clave)
    accion = request.POST.get("accion")
    ctx = {"titulo": f"Cargar reporte de {plataforma}", "plataforma": plataforma, "extensiones": extensiones,
           "ayuda": ayuda, "empresas": Empresa.objects.all(), "NUEVA": NUEVA}

    if request.method == "POST" and accion == "subir":
        archivo = request.FILES.get("archivo")
        eleccion = request.POST.get("empresa")
        nueva = " ".join(request.POST.get("empresa_nueva", "").split())
        if not archivo:
            messages.error(request, "Elige un archivo.")
            return redirect(request.path)
        if eleccion == NUEVA and not nueva:
            messages.error(request, "Escribe el nombre de la nueva empresa.")
            return redirect(request.path)
        ruta = _carpeta() / f"{uuid.uuid4().hex}{Path(archivo.name).suffix.lower()}"
        with ruta.open("wb") as f:
            for parte in archivo.chunks():
                f.write(parte)
        try:
            _leer({"ruta": str(ruta), "nombre": archivo.name}, importador)
        except ValueError as e:
            ruta.unlink(missing_ok=True)
            messages.error(request, str(e))
            return redirect(request.path)
        request.session[clave] = {"ruta": str(ruta), "nombre": archivo.name,
                                  "empresa": None if eleccion == NUEVA else eleccion, "nueva": nueva}
        return redirect(request.path)

    if request.method == "POST" and accion == "cancelar" and sesion:
        Path(sesion["ruta"]).unlink(missing_ok=True)
        request.session.pop(clave, None)
        return redirect(request.path)

    if not sesion or not Path(sesion["ruta"]).exists():
        request.session.pop(clave, None)
        return render(request, plantilla, ctx)

    # Paso 2: revisar campañas del archivo (incluir / renombrar) y guardar.
    df = _leer(sesion, importador)
    empresa = Empresa.objects.filter(pk=sesion["empresa"]).first() if sesion["empresa"] else None
    grupos = analisis.agrupar_campanas(df["campana"].unique())
    df = df.assign(_campana=df["campana"].map(grupos))
    lista = (df.groupby("_campana", sort=False).agg(envios=("campana", "nunique"), mensajes=("campana", "size"))
             .reset_index())
    enviado = request.method == "POST"
    nombres, filas_campanas = {}, []
    for i, f in enumerate(lista.itertuples()):
        incluir = (request.POST.get(f"incluir_{i}") == "1") if enviado else True
        nombre = (request.POST.get(f"nombre_{i}") or "").strip() or f._1
        filas_campanas.append({"i": i, "original": f._1, "nombre": nombre, "incluir": incluir, "envios": f.envios,
                               "mensajes": f.mensajes})
        if incluir:
            nombres[f._1] = nombre
    ctx.update({"sesion": sesion, "empresa_obj": empresa, "campanas_archivo": filas_campanas})
    if not nombres:
        messages.warning(request, "Marca al menos una campaña para cargar.")
        return render(request, plantilla, ctx)

    df = df[df["_campana"].isin(nombres)].copy()
    cambia = df["_campana"].map(nombres) != df["_campana"]
    df.loc[cambia, "campana"] = [analisis.renombrar_envio(e, nombres[c])
                                 for e, c in zip(df.loc[cambia, "campana"], df.loc[cambia, "_campana"])]
    df["_campana"] = df["_campana"].map(nombres)

    # Datos de cada campaña (categoría, solicitante, fecha): lo ya guardado o lo que diga el archivo.
    datos_campanas, bloques = {}, []
    numero = {}  # nombre final -> número de la campaña en el archivo (estable aunque se desmarquen otras)
    for f in filas_campanas:
        if f["incluir"]:
            numero.setdefault(f["nombre"], f["i"])
    for campana, grupo in df.groupby("_campana", sort=False):
        j = numero[campana]
        envios = list(grupo["campana"].unique())
        previa = Campana.objects.filter(plataforma=plataforma, nombre__in=envios, empresa=empresa).first() \
            if empresa else None
        cat_archivo = grupo["categoria_plantilla"].dropna() if "categoria_plantilla" in grupo else pd.Series(dtype=str)
        categoria = request.POST.get(f"cat_{j}") or (previa.categoria if previa else None) or \
            (cat_archivo.iloc[0] if not cat_archivo.empty else "UTILITY")
        quien = request.POST.get(f"quien_{j}", previa.solicitado_por if previa else "") or ""
        fecha = request.POST.get(f"fecha_{j}") or (previa.fecha_solicitud.isoformat()
                                                   if previa and previa.fecha_solicitud else "")
        bloques.append({"j": j, "campana": campana, "envios": len(envios), "mensajes": len(grupo),
                        "existia": bool(previa), "categoria": categoria.upper(), "quien": quien, "fecha": fecha})
        for e in envios:
            datos_campanas[e] = {"categoria": categoria, "solicitado_por": quien.strip() or None,
                                 "fecha_solicitud": date.fromisoformat(fecha) if fecha else None}

    if accion == "guardar":
        if empresa is None:
            empresa, _ = Empresa.objects.get_or_create(nombre=sesion["nueva"])
        nuevas, actualizadas, sin_cambios = cargas.guardar(
            df, plataforma, empresa, sesion["nombre"], datos_campanas, origen="manual",
            usuario=request.user.get_username())
        Path(sesion["ruta"]).unlink(missing_ok=True)
        request.session.pop(clave, None)
        partes = [f"{nuevas:,} mensajes nuevos"] + ([f"{actualizadas:,} actualizados"] if actualizadas else []) + \
                 ([f"{sin_cambios:,} sin cambios"] if sin_cambios else [])
        messages.success(request, f"Guardado en {empresa}: " + ", ".join(partes) + ".")
        return redirect(request.path)

    comp = cargas.comparar(df, plataforma, empresa) if empresa else pd.DataFrame()
    ya_estaba = not comp.empty and comp["sin_cambios"].sum() + comp["actualizadas"].sum() > 0
    sin_novedad = ya_estaba and comp["nuevas"].sum() == 0 and comp["actualizadas"].sum() == 0
    if not comp.empty:
        comp = comp.assign(fallidos=comp["fallidos_antes"].astype(str) + " → " + comp["fallidos_despues"].astype(str))
        comp = comp[["campana", "mensajes", "nuevas", "actualizadas", "sin_cambios", "entregados", "leidos",
                     "respuestas", "opt_outs", "fallidos"]].rename(columns={
                         "campana": "Campaña", "mensajes": "Mensajes en archivo", "nuevas": "Nuevos",
                         "actualizadas": "Con cambios", "sin_cambios": "Sin cambios", "entregados": "Entregados (+)",
                         "leidos": "Leídos (+)", "respuestas": "Respuestas (+)", "opt_outs": "Opt-outs (+)",
                         "fallidos": "Fallidos (antes → después)"})
    ctx.update({
        "bloques": bloques, "categorias": analisis.CATEGORIAS, "solicitantes": sorted(
            {s for s in Campana.objects.exclude(solicitado_por=None).values_list("solicitado_por", flat=True) if s}),
        "comparacion": tabla(comp, presentar=False) if ya_estaba else None, "sin_novedad": sin_novedad,
        "ultima": cargas.ultima_carga(sesion["nombre"], empresa) if empresa and sin_novedad else None,
        "previa": [{"nombre": "Mensajes", "valor": f"{len(df):,}"}] + [
            {"nombre": e, "valor": f"{int((df['estado'] == e).sum()):,}"} for e in ["Leído", "Entregado", "Enviado",
                                                                                    "Fallido"]],
        "texto_guardar": "Guardar actualización" if ya_estaba else "Guardar reporte",
    })
    return render(request, plantilla, ctx)
