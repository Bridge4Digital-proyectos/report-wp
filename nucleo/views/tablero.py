"""Dashboard, vista de UNA campaña, gráficos (JSON para plotly.js) y la tabla de quienes respondieron."""
import json
from urllib.parse import urlencode

import pandas as pd
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from nucleo import filtros
from nucleo.presentacion import tabla
from nucleo.servicios import analisis, datos, graficos, indicadores
from nucleo.servicios import respuestas as R

# Gráficos clicables: (eje del valor elegido, parámetro de la URL).
CLIC = {"sentido": ("y", "sentido"), "tipos_respuesta": ("y", "tipo"), "calificaciones": ("x", "nota"),
        "motivos": ("y", "motivo")}
VACIOS = {"errores": "Esta campaña no tuvo errores.",
          "motivos": "Las respuestas de esta campaña no traen opciones ni motivos.",
          "horario_entrega": "No hay mensajes entregados en este periodo.",
          "mapa_lectura": "No hay mensajes leídos en este periodo."}
SIN_CAMPANA = {"categorias", "horario_entrega", "mapa_lectura"}  # gráficos que también van en el Dashboard general


def _dinero(x, moneda="", decimales=2) -> str:
    return "—" if x is None or pd.isna(x) else f"{x:,.{decimales}f}{' ' + moneda if moneda else ''}"


def _vista_ingresos(df: pd.DataFrame, tarifas: dict) -> dict | None:
    """Ingresos de Bridge4 de todas las difusiones del Dashboard (con los filtros): totales, por categoría,
    por mes y por campaña. Uso interno: la empresa ve estos mismos montos como costos en sus reportes."""
    d = indicadores.montos_detalle(df, tarifas)
    if d is None:
        return None
    m = d["moneda"]
    empresa = df["empresa"].iloc[0]
    mayor = d["por_campana"]["monto"].max() or 1
    campanas = [{
        "campana": r.difusion, "categoria": r.categoria,
        "inicio": pd.Timestamp(r.inicio).strftime("%d/%m/%Y") if pd.notna(r.inicio) else "—",
        "entregados": f"{int(r.entregados):,}", "respondieron": f"{int(r.respondieron):,}",
        "monto": _dinero(r.monto), "pct": f"{r.pct:.1%}", "ancho": f"{100 * r.monto / mayor:.1f}",
        "por_entregado": _dinero(r.por_entregado, decimales=4), "por_respuesta": _dinero(r.por_respuesta),
        "url": f"?{urlencode({'empresa': empresa, 'campana': r.difusion})}#campana",
    } for r in d["por_campana"].itertuples()]

    def filas(t, nombre):
        return [{"nombre": getattr(r, nombre), "entregados": f"{int(r.entregados):,}", "monto": _dinero(r.monto),
                 "pct": f"{r.pct:.1%}", "por_respuesta": _dinero(r.por_respuesta),
                 "tarifa": getattr(r, "tarifa", None)} for r in t.itertuples()]

    mensual = d["por_mes"]["monto"]
    return {
        "moneda": m, "campanas_n": d["campanas"], "total": _dinero(d["total"], m),
        "promedio_mes": _dinero(mensual.mean(), m) if len(mensual) else "—",
        "promedio_campana": _dinero(d["total"] / d["campanas"], m) if d["campanas"] else "—",
        "por_entregado": _dinero(d["por_entregado"], m, 4),
        "por_categoria": filas(d["por_categoria"], "categoria"), "por_mes": filas(d["por_mes"], "mes"),
        "por_campana": campanas,
    }


def contexto_indicadores(df: pd.DataFrame, qs: str, a: pd.DataFrame | None = None, campana: str | None = None) -> dict:
    """Indicadores clave, horario, mapa de lectura, calidad de base y costo (Dashboard general o una campaña).

    `a` (respuestas interpretadas) solo se pasa en la vista de una campaña: la satisfacción depende de su encuesta.
    """
    empresa = df["empresa"].iloc[0]
    tarifas = indicadores.tarifas_de(empresa)
    ind = indicadores.calcular(df, a, tarifas)
    extra = f"&{urlencode({'campana': campana})}" if campana else ""

    def tarjeta(clave):
        return {"clave": clave, "titulo": graficos.TITULOS[clave], "alto": graficos.alto(clave, df),
                "url": f"{reverse('grafico', args=[clave])}?{qs}{extra}", "clic": False}

    cal = ind["calidad"]
    mayor = max([f["n"] for f in cal["filas"]] or [1]) or 1
    sat = ind["satisfaccion"]
    costo = ind["costo"]
    return {
        "ind_tarjetas": indicadores.tarjetas(ind),
        "ind_graficos": [tarjeta("horario_entrega"), tarjeta("mapa_lectura")],
        "ind_calidad": {
            "filas": [{**f, "n_txt": indicadores.num(f["n"]), "pct_txt": indicadores.pct(f["pct"]),
                       "ancho": f"{100 * f['n'] / mayor:.1f}"} for f in cal["filas"]],
            "numeros_repetidos": indicadores.num(cal["numeros_repetidos"]),
            "pct_problemas": indicadores.pct(cal["pct_problemas"]),
            "contactos_validos": indicadores.num(cal["contactos_validos"]),
            "hay_repetidos": cal["numeros_repetidos"] > 0,
        },
        "ind_satisfaccion": {
            "csat": indicadores.pct(sat["csat"]) if "csat" in sat else None,
            "promedio": f"{sat['promedio']:.1f}" if "promedio" in sat else None,
            "calificaron": indicadores.num(sat["calificaron"]) if "calificaron" in sat else None,
            "neto": (f"{sat['sentimiento_neto'] * 100:+.1f} pts" if "sentimiento_neto" in sat else None),
            "positivas": indicadores.num(sat.get("positivas", 0)), "negativas": indicadores.num(sat.get("negativas", 0)),
        } if sat else None,
        "ind_costo": {
            **costo,
            "total_txt": f"{costo['total']:,.2f} {costo['moneda']}" if costo.get("disponible") else None,
            "por_entregado_txt": (f"{costo['por_entregado']:,.4f} {costo['moneda']}"
                                  if costo.get("por_entregado") is not None else "—"),
            "por_respuesta_txt": (f"{costo['por_respuesta']:,.2f} {costo['moneda']}"
                                  if costo.get("por_respuesta") is not None else "—"),
        } if costo else None,
        "ind_ingresos": _vista_ingresos(df, tarifas) if campana is None else None,
        "url_repetidos": f"{reverse('repetidos')}?{qs}{extra}",
        "url_ingresos": f"{reverse('ingresos_excel')}?{qs}",
        "url_tarifas": f"{reverse('tarifas')}?{urlencode({'empresa': empresa})}",
    }


def kpis(df) -> list[dict]:
    return [{"nombre": n, "valor": f"{v:,}", "pct": f"{p:.1%}" if p is not None else None}
            for n, (v, p) in analisis.kpis(df).items()]


def de_campana(df: pd.DataFrame, campana: str | None) -> pd.DataFrame | None:
    if not campana:
        return None
    dc = df[df["difusion"] == campana]
    return dc if not dc.empty else None


def contexto_campana(df_c: pd.DataFrame, qs: str, respuestas: bool = True) -> dict:
    """Todo lo que necesita la plantilla de la vista de una campaña (los gráficos se piden aparte).

    respuestas=False deja fuera la información de las respuestas de los clientes (encuesta y quién respondió)."""
    empresa, nombre = df_c["empresa"].iloc[0], df_c["difusion"].iloc[0]
    info = analisis.informe_campanas(df_c).iloc[0]
    a = datos.respuestas(df_c)
    base = f"{qs}&{urlencode({'campana': nombre})}"

    def tarjeta(clave):
        return {"clave": clave, "titulo": graficos.TITULOS[clave],
                "alto": graficos.alto(clave, df_c, a if not a.empty else None),
                "url": f"{reverse('grafico', args=[clave])}?{base}", "clic": clave in CLIC}

    hay_respuestas = respuestas and not a.empty
    return {
        "c_nombre": nombre, "c_empresa": empresa, "c_info": {
            "categoria": info["categoria"], "solicitado_por": info["solicitado_por"],
            "fecha_solicitud": info["fecha_solicitud"] if pd.notna(info["fecha_solicitud"]) else None,
            "primer_envio": pd.Timestamp(info["primer_envio"]), "mensajes_lote": int(info["mensajes_lote"]),
            "pruebas": int(info["pruebas"]), "mensajes_prueba": int(info["mensajes_prueba"])},
        "c_kpis": kpis(df_c),
        "c_envio": [tarjeta("embudo"), tarjeta("resultado_envio")],
        "c_errores": tarjeta("errores"),
        "c_detalle": tabla(analisis.por_campana(df_c)),
        "c_hay_respuestas": hay_respuestas, "c_con_respuestas": respuestas,
        "c_resp_pares": [tarjeta("sentido"), tarjeta("tipos_respuesta")] if hay_respuestas else [],
        "c_resp_solas": ([tarjeta("calificaciones")] if hay_respuestas and a["calificacion"].notna().any() else [])
        + ([tarjeta("motivos")] if hay_respuestas else []),
        "c_url_respondieron": f"{reverse('respondieron')}?{base}",
        "c_url_significados": f"{reverse('significados')}?{urlencode({'empresa': empresa, 'campana': nombre})}",
        "c_ind": contexto_indicadores(df_c, qs, a if respuestas else None, nombre),
    }


def dashboard(request):
    todo = datos.mensajes()
    df, elegido, ctx = filtros.aplicar(request, todo)
    ctx.update({"titulo": "Dashboard", "sin_datos": todo.empty, "vacio": df.empty})
    if df.empty:
        return render(request, "nucleo/dashboard.html", ctx)
    campana = request.GET.get("campana")
    resumen = analisis.por_difusion(df)
    qs = ctx["qs"]
    ctx.update({
        "kpis": kpis(df),
        "dona": {"clave": "categorias", "titulo": graficos.TITULOS["categorias"], "alto": graficos.alto("categorias"),
                 "url": f"{reverse('grafico', args=['categorias'])}?{qs}", "clic": False},
        "por_categoria": tabla(analisis.por_categoria(df)),
        "g_ind": contexto_indicadores(df, qs),
        "resumen": tabla(resumen, ocultar=("Empresa", "Plataforma"),
                         enlaces=lambda f: f"?{qs}&{urlencode({'campana': f['difusion']})}#campana",
                         elegida=lambda f: f["difusion"] == campana),
    })
    df_c = de_campana(df, campana)
    if df_c is not None:
        ctx.update(contexto_campana(df_c, qs))
    return render(request, "nucleo/dashboard.html", ctx)


def _fabricar(nombre, df, df_c):
    if nombre == "categorias":
        return graficos.categorias(df)
    if nombre == "horario_entrega":
        return graficos.horario_entrega(df_c if df_c is not None else df)
    if nombre == "mapa_lectura":
        return graficos.mapa_lectura(df_c if df_c is not None else df)
    if df_c is None:
        raise Http404("Elige una campaña.")
    if nombre == "embudo":
        return graficos.embudo(df_c)
    if nombre == "resultado_envio":
        return graficos.resultado_por_envio(df_c)
    if nombre == "errores":
        return graficos.errores(df_c)
    a = datos.respuestas(df_c)
    if a.empty:
        return None
    return {"sentido": graficos.sentido, "tipos_respuesta": graficos.tipos_respuesta,
            "calificaciones": graficos.calificaciones, "motivos": graficos.motivos}[nombre](a)


def grafico(request, nombre):
    if nombre not in graficos.TITULOS:
        raise Http404
    df, _, _ = filtros.aplicar(request, datos.mensajes())
    g = _fabricar(nombre, df, de_campana(df, request.GET.get("campana")))
    if g is None:
        return JsonResponse({"vacio": VACIOS.get(nombre, "Sin datos para mostrar.")})
    fig = g.fig.update_layout(template="plotly_white", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    eje, parametro = CLIC.get(nombre, (None, None))
    return JsonResponse({"fig": json.loads(fig.to_json()), "subtitulo": (fig.layout.meta or {}).get("subtitulo"),
                         "explicacion": g.explicacion, "eje": eje, "parametro": parametro})


def _respondieron(request):
    df, _, _ = filtros.aplicar(request, datos.mensajes())
    df_c = de_campana(df, request.GET.get("campana"))
    if df_c is None:
        raise Http404("Elige una campaña.")
    a = datos.respuestas(df_c)
    g = request.GET
    m = pd.Series(True, index=a.index)
    partes = []
    if sentidos := g.getlist("sentido"):
        m &= a["sentido"].isin(sentidos)
        partes.append("sentido: " + ", ".join(sentidos))
    if tipos := g.getlist("tipo"):
        m &= a["tipo"].isin(tipos)
        partes.append("tipo: " + ", ".join(tipos))
    if notas := g.getlist("nota"):
        m &= a["calificacion"].isin([int(float(n)) for n in notas])
        partes.append("calificación: " + ", ".join(notas))
    if motivos := g.getlist("motivo"):
        m &= a["motivos"].map(lambda ms: any(x in ms for x in motivos))
        partes.append("respuesta: " + ", ".join(motivos))
    return a[m], partes


def respondieron(request):
    """Tabla de los clientes que respondieron como las barras elegidas (fragmento HTML)."""
    elegidos, partes = _respondieron(request)
    lista = R.lista_legible(elegidos)
    return render(request, "nucleo/_respondieron.html", {
        "partes": partes, "total": f"{len(lista):,}", "t": tabla(lista, presentar=False),
        "csv": f"{reverse('respondieron_csv')}?{request.GET.urlencode()}"})


def repetidos(request):
    """Excel con los números que recibieron el mensaje más de una vez (campaña elegida o empresa filtrada)."""
    from io import BytesIO

    df, elegido, _ = filtros.aplicar(request, datos.mensajes())
    campana = request.GET.get("campana")
    alcance = de_campana(df, campana) if campana else df
    if alcance is None:
        raise Http404("No se encontró la campaña.")
    tabla_rep = indicadores.repetidos(alcance)
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        tabla_rep.to_excel(xw, sheet_name="Números repetidos", index=False)
        hoja = xw.sheets["Números repetidos"]
        hoja.freeze_panes = "A2"
        if len(tabla_rep):
            hoja.auto_filter.ref = hoja.dimensions
        for col, ancho in zip("ABCDEFGH", [16, 8, 50, 70, 20, 20, 11, 11]):
            hoja.column_dimensions[col].width = ancho
        filtros_txt = {**elegido, **({"Campaña": campana} if campana else {})}
        pd.DataFrame(list(filtros_txt.items()), columns=["Filtro", "Valor"]).to_excel(
            xw, sheet_name="Filtros", index=False)
    nombre = f"numeros_repetidos_{elegido.get('Empresa', '')}".replace(" ", "_")
    resp = HttpResponse(buf.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="{nombre}.xlsx"'
    return resp


def ingresos_excel(request):
    """Excel interno con los ingresos de Bridge4 de todas las difusiones del Dashboard: por campaña, mes y categoría."""
    from io import BytesIO

    df, elegido, _ = filtros.aplicar(request, datos.mensajes())
    if df.empty:
        raise Http404("No hay mensajes con esos filtros.")
    empresa = df["empresa"].iloc[0]
    d = indicadores.montos_detalle(df, indicadores.tarifas_de(empresa))
    if d is None:
        raise Http404("Faltan precios para calcular los ingresos.")
    m = d["moneda"]
    nombres = {"difusion": "Campaña", "categoria": "Categoría", "inicio": "Primer envío", "mes": "Mes",
               "enviados": "Enviados", "entregados": "Entregados", "leidos": "Leídos", "respondieron": "Respondieron",
               "tarifa": f"Precio ({m})", "monto": f"Ingreso ({m})", "pct": "% del ingreso",
               "por_entregado": f"Ingreso por entregado ({m})", "por_respuesta": f"Ingreso por respuesta ({m})"}
    hojas = {
        "Por campaña": d["por_campana"][["difusion", "categoria", "inicio", "enviados", "entregados", "leidos",
                                         "respondieron", "monto", "pct", "por_entregado", "por_respuesta"]],
        "Por mes": d["por_mes"][["mes", "enviados", "entregados", "respondieron", "monto", "pct", "por_respuesta"]],
        "Por categoría": d["por_categoria"][["categoria", "tarifa", "entregados", "monto", "pct"]],
    }
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for nombre, tabla_ in hojas.items():
            tabla_ = tabla_.rename(columns=nombres)
            tabla_.to_excel(xw, sheet_name=nombre, index=False)
            hoja = xw.sheets[nombre]
            hoja.freeze_panes = "A2"
            for i, col in enumerate(tabla_.columns, start=1):
                letra = hoja.cell(1, i).column_letter
                hoja.column_dimensions[letra].width = 60 if col == "Campaña" else 18
                formato = ("0.0%" if col.startswith("%") else "#,##0.0000" if "por entregado" in col else
                           "#,##0.00" if f"({m})" in col else "dd/mm/yyyy" if col == "Primer envío" else
                           "#,##0" if col in ("Enviados", "Entregados", "Leídos", "Respondieron") else None)
                if formato:
                    for celda in hoja[letra][1:]:
                        celda.number_format = formato
        resumen = {**elegido, "Ingreso total": f"{d['total']:,.2f} {m}", "Campañas": d["campanas"]}
        pd.DataFrame(list(resumen.items()), columns=["Dato", "Valor"]).to_excel(xw, sheet_name="Resumen", index=False)
    resp = HttpResponse(buf.getvalue(),
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    resp["Content-Disposition"] = f'attachment; filename="ingresos_{empresa.replace(" ", "_")}.xlsx"'
    return resp


def respondieron_csv(request):
    elegidos, _ = _respondieron(request)
    resp = HttpResponse(R.lista_legible(elegidos).to_csv(index=False).encode("utf-8-sig"), content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="respondieron.csv"'
    return resp
