"""Informe, Campañas (datos y significados), Empresas e Historial."""
from datetime import date, datetime
from urllib.parse import urlencode

import pandas as pd
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from connectly.models import CuentaConnectly, Sincronizacion
from nucleo import filtros
from nucleo.models import Campana, Carga, Empresa, Mensaje, Significado
from nucleo.presentacion import tabla
from nucleo.servicios import analisis, datos
from nucleo.servicios import respuestas as R
from nucleo.servicios.respaldo import respaldar
from nucleo.views.tablero import contexto_campana

# ---------------------------------------------------------------- Informe


def _informe(request):
    df, elegido, ctx = filtros.aplicar(request, datos.mensajes())
    opciones = analisis.campanas_de(df) if not df.empty else []
    tamanos = df.groupby("difusion").size() if not df.empty else {}
    elegidas = [c for c in request.GET.getlist("c") if c in {d for _, d in opciones}]
    secciones = request.GET.getlist("s") or analisis.SECCIONES
    secciones = [s for s in secciones if s in analisis.SECCIONES]
    return df, elegido, ctx, opciones, tamanos, elegidas, secciones


def informe(request):
    df, elegido, ctx, opciones, tamanos, elegidas, secciones = _informe(request)
    ctx.update({"titulo": "Informe", "vacio": df.empty,
                "secciones_todas": [s for s in analisis.SECCIONES if s != "Respuestas de clientes"],
                "con_respuestas": "Respuestas de clientes" in secciones,
                "secciones": secciones, "elegidas": elegidas,
                "opciones": [{"difusion": d, "mensajes": f"{int(tamanos[d]):,}"} for _, d in opciones]})
    if df.empty:
        return render(request, "nucleo/informe.html", ctx)
    if not elegidas:
        ctx["disponibles"] = tabla(analisis.informe_campanas(df), ocultar=("Empresa",))
        return render(request, "nucleo/informe.html", ctx)
    d = df[df["difusion"].isin(elegidas)]
    qs = request.GET.urlencode()
    ctx.update({
        "generales": [{"nombre": n, "tabla": tabla(t, presentar=False)} for n, t in analisis.secciones(d, secciones).items()],
        "url_excel": f"{reverse('informe_archivo', args=['excel'])}?{qs}",
        "url_pdf": f"{reverse('informe_archivo', args=['pdf'])}?{qs}",
        "una": len(elegidas) == 1,
        "filtros_txt": [(k, v) for k, v in elegido.items()],
    })

    if len(elegidas) == 1:
        ctx.update(contexto_campana(d, ctx["qs"], respuestas="Respuestas de clientes" in secciones))
    elif {"Respuestas de clientes", "Errores"} & set(secciones):
        ctx["por_campana"] = [{**b, "t_respuestas": tabla(b["respuestas"], presentar=False) if "respuestas" in b else None,
                               "t_errores": tabla(b["errores"], presentar=False) if "errores" in b else None}
                              for b in analisis.por_campana_informe(d, secciones)]
    return render(request, "nucleo/informe.html", ctx)


def informe_archivo(request, tipo):
    df, elegido, _, _, _, elegidas, secciones = _informe(request)
    d = df[df["difusion"].isin(elegidas)]
    elegido = {**elegido, "Campañas": "; ".join(elegidas)}
    marca = datetime.now().strftime("%Y%m%d_%H%M")
    if tipo == "excel":
        contenido = analisis.excel_bytes(d, secciones, elegido)
        resp = HttpResponse(contenido, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        resp["Content-Disposition"] = f'attachment; filename="informe_campanas_{marca}.xlsx"'
    else:
        resp = HttpResponse(analisis.pdf_bytes(d, secciones, elegido), content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="informe_campanas_{marca}.pdf"'
    return resp

# ---------------------------------------------------------------- Campañas


def _empresa_elegida(request, empresas):
    nombre = request.GET.get("empresa") or request.POST.get("empresa") or request.session.get("empresa")
    if nombre not in empresas:
        nombre = empresas[0] if empresas else None
    request.session["empresa"] = nombre
    return nombre


def campanas(request):
    todas = datos.campanas()
    empresas = sorted(todas["empresa"].unique()) if not todas.empty else []
    empresa = _empresa_elegida(request, empresas)
    ctx = {"titulo": "Campañas", "pestana": "datos", "empresas": empresas, "empresa": empresa}
    if request.method == "POST":
        cambios = 0
        with transaction.atomic():
            for c in Campana.objects.filter(id__in=request.POST.getlist("id")):
                cat = request.POST.get(f"cat_{c.id}", c.categoria).upper()
                quien = request.POST.get(f"quien_{c.id}", "").strip() or None
                fecha = request.POST.get(f"fecha_{c.id}") or None
                fecha = date.fromisoformat(fecha) if fecha else None
                if (cat, quien, fecha) != (c.categoria, c.solicitado_por, c.fecha_solicitud):
                    c.categoria, c.solicitado_por, c.fecha_solicitud = cat, quien, fecha
                    c.save()
                    cambios += 1
        if cambios:
            datos.cambiaron()
        messages.success(request, f"{cambios} envío(s) actualizado(s)." if cambios else "No había cambios.")
        return redirect(f"{request.path}?{request.GET.urlencode()}")
    if todas.empty:
        return render(request, "nucleo/campanas.html", ctx)
    t = todas[todas["empresa"] == empresa].copy()
    t["mes"] = analisis.etiqueta_mes(t["primer_envio"]).values
    meses = [m for m in request.GET.getlist("mes") if m in set(t["mes"])]
    ctx.update({"opciones_mes": analisis.meses_ordenados(t["primer_envio"]), "meses": meses})
    if meses:
        t = t[t["mes"].isin(meses)]
    ctx["filas"] = [{**r, "primer_envio": pd.Timestamp(r["primer_envio"]) if pd.notna(r["primer_envio"]) else None,
                     "fecha_solicitud": r["fecha_solicitud"].isoformat() if pd.notna(r["fecha_solicitud"]) and
                     r["fecha_solicitud"] else ""} for r in t.to_dict("records")]
    ctx["categorias"] = analisis.CATEGORIAS
    return render(request, "nucleo/campanas.html", ctx)


def significados(request):
    todo = datos.mensajes()
    empresas = sorted(todo["empresa"].unique()) if not todo.empty else []
    empresa = _empresa_elegida(request, empresas)
    ctx = {"titulo": "Campañas", "pestana": "significados", "empresas": empresas, "empresa": empresa,
           "sentidos": R.SENTIDOS}
    a = datos.respuestas(todo[todo["empresa"] == empresa]) if empresa else pd.DataFrame()
    if a.empty:
        return render(request, "nucleo/significados.html", ctx)
    conteo = a.groupby("difusion").size().sort_values(ascending=False)
    campana = request.GET.get("campana") or request.POST.get("campana")
    if campana not in conteo.index:
        campana = conteo.index[0]
    conf = datos.significados().get((empresa, datos.normalizar(campana)), {})

    if request.method == "POST":
        if request.POST.get("accion") == "restablecer":
            datos.borrar_significados(empresa, campana)
            messages.success(request, "Se volvió a la sugerencia automática.")
        else:
            valores = request.POST.getlist("valor")
            filas = [(v, request.POST.get(f"sig_{i}", ""), request.POST.get(f"sen_{i}", R.NEUTRAL))
                     for i, v in enumerate(valores)]
            datos.guardar_significados(empresa, campana, filas)
            messages.success(request, "Guardado. El Dashboard y el Informe ya usan estos significados.")
        return redirect(f"{request.path}?{urlencode({'empresa': empresa, 'campana': campana})}")

    valores = R.valores_campana(a, empresa, campana, conf)
    ctx.update({"campanas": [{"difusion": d, "respuestas": f"{int(n):,}"} for d, n in conteo.items()],
                "campana": campana, "configurada": bool(conf),
                "filas": [{"i": i, **r} for i, r in enumerate(valores.to_dict("records"))]})
    return render(request, "nucleo/significados.html", ctx)

# ---------------------------------------------------------------- Empresas


def empresas(request):
    if request.method == "POST":
        if request.POST.get("accion") == "crear":
            nombre = " ".join(request.POST.get("nombre", "").split())
            if not nombre:
                messages.error(request, "Escribe un nombre.")
            elif Empresa.objects.filter(nombre__iexact=nombre).exists():
                messages.warning(request, f"La empresa «{nombre}» ya existe.")
            else:
                Empresa.objects.create(nombre=nombre)
                messages.success(request, f"Empresa «{nombre}» creada.")
        else:
            cambios, errores = 0, []
            for e in Empresa.objects.all():
                nuevo = " ".join(request.POST.get(f"nombre_{e.id}", e.nombre).split())
                if nuevo == e.nombre:
                    continue
                if not nuevo:
                    errores.append(f"«{e.nombre}»: el nombre no puede quedar vacío.")
                elif Empresa.objects.filter(nombre__iexact=nuevo).exclude(pk=e.pk).exists():
                    errores.append(f"Ya existe otra empresa llamada «{nuevo}».")
                else:
                    e.nombre = nuevo
                    e.save()
                    cambios += 1
            for err in errores:
                messages.error(request, err)
            if cambios:
                datos.cambiaron()
                messages.success(request, f"{cambios} empresa(s) renombrada(s).")
        return redirect("empresas")
    filas = [{**e, "ultimo_envio": e["ultimo_envio"]} for e in datos.resumen_empresas()]
    return render(request, "nucleo/empresas.html", {"titulo": "Empresas", "filas": filas})

# ---------------------------------------------------------------- Historial


def historial(request):
    if request.method == "POST":
        if request.POST.get("confirmar", "").strip() != "BORRAR":
            messages.error(request, "Escribe BORRAR para confirmar.")
            return redirect("historial")
        ruta = respaldar("antes_de_borrar")
        with transaction.atomic():
            Significado.objects.all().delete()
            Mensaje.objects.all().delete()
            Carga.objects.all().delete()
            Campana.objects.all().delete()
            Sincronizacion.objects.all().delete()
            con_cuenta = CuentaConnectly.objects.values_list("empresa_id", flat=True)
            Empresa.objects.exclude(id__in=con_cuenta).delete()
        datos.cambiaron()
        messages.success(request, f"Se borraron todos los datos. Respaldo guardado en {ruta.name}.")
        return redirect("historial")
    cargas = Carga.objects.select_related("empresa")
    meses_disp = analisis.meses_ordenados(pd.Series([c.fecha_carga for c in cargas]))
    meses = request.GET.getlist("mes")
    filas = [c for c in cargas if not meses or analisis.etiqueta_mes(pd.Series([c.fecha_carga])).iloc[0] in meses]
    ctx = {"titulo": "Historial de cargas", "filas": filas, "opciones_mes": meses_disp, "meses": meses,
           "metricas": [{"nombre": "Empresas", "valor": f"{Empresa.objects.count():,}"},
                        {"nombre": "Envíos (lotes y pruebas)", "valor": f"{Campana.objects.count():,}"},
                        {"nombre": "Mensajes", "valor": f"{Mensaje.objects.count():,}"}]}
    return render(request, "nucleo/historial.html", ctx)


# ---------------------------------------------------------------- Tarifas por empresa


def tarifas(request):
    """Precio que Bridge4 cobra a cada empresa por mensaje entregado de cada categoría de Meta.
    En el Dashboard da los ingresos de Bridge4; en los reportes de la empresa, su costo."""
    from decimal import Decimal, InvalidOperation

    from nucleo.models import CATEGORIAS, Tarifa

    lista = list(Empresa.objects.all())
    nombre = request.GET.get("empresa") or request.POST.get("empresa")
    empresa = next((e for e in lista if e.nombre == nombre), lista[0] if lista else None)
    if empresa is None:
        return redirect("empresas")
    if request.method == "POST":
        moneda = request.POST.get("moneda") if request.POST.get("moneda") in dict(Tarifa.MONEDAS) else "USD"
        errores, guardadas = [], 0
        with transaction.atomic():
            for cat, _ in CATEGORIAS:
                texto = request.POST.get(f"precio_{cat}", "").strip().replace(",", ".")
                if not texto:
                    Tarifa.objects.filter(empresa=empresa, categoria=cat).delete()
                    continue
                try:
                    precio = Decimal(texto)
                    if precio < 0:
                        raise InvalidOperation
                except InvalidOperation:
                    errores.append(f"{cat}: «{texto}» no es un precio válido.")
                    continue
                Tarifa.objects.update_or_create(empresa=empresa, categoria=cat,
                                                defaults={"precio": precio, "moneda": moneda})
                guardadas += 1
        for e in errores:
            messages.error(request, e)
        if not errores:
            messages.success(request, f"Precios de {empresa} guardados ({guardadas} categoría(s)).")
        return redirect(f"{request.path}?{urlencode({'empresa': empresa.nombre})}")
    actuales = {t.categoria: t for t in Tarifa.objects.filter(empresa=empresa)}
    moneda = next(iter(actuales.values())).moneda if actuales else "USD"
    return render(request, "nucleo/tarifas.html", {
        "titulo": "Tarifas", "empresas": lista, "empresa": empresa, "moneda": moneda, "monedas": Tarifa.MONEDAS,
        "filas": [{"categoria": c, "precio": (f"{actuales[c].precio.normalize():f}" if c in actuales else ""),
                   "actualizado": actuales[c].actualizado if c in actuales else None} for c, _ in CATEGORIAS]})
