"""Métricas del informe y exportación a Excel y PDF."""
import re
from io import BytesIO

import pandas as pd

SECCIONES = ["Resumen general", "Por campaña", "Errores", "Respuestas de clientes"]

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto",
         "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def etiqueta_mes(fechas) -> pd.Series:
    """'Noviembre 2026' para cada fecha (vacío si no hay fecha). No depende del idioma del sistema."""
    f = pd.to_datetime(pd.Series(fechas), errors="coerce", format="mixed")
    return f.map(lambda x: f"{MESES[x.month - 1]} {x.year}" if pd.notna(x) else "")


def meses_ordenados(fechas) -> list[str]:
    """Meses presentes en las fechas, del más reciente al más antiguo."""
    f = pd.to_datetime(pd.Series(fechas), errors="coerce", format="mixed").dropna()
    periodos = sorted(f.dt.to_period("M").unique(), reverse=True)
    return [f"{MESES[p.month - 1]} {p.year}" for p in periodos]

ETIQUETAS = {
    "empresa": "Empresa", "difusiones": "Difusiones", "mensajes": "Mensajes", "plataforma": "Plataforma", "campana": "Campaña", "categoria": "Categoría",
    "solicitado_por": "Solicitado por", "fecha_solicitud": "Fecha de solicitud", "primer_envio": "Primer envío",
    "total": "Total mensajes", "enviados": "Enviados", "entregados": "Entregados", "leidos": "Leídos",
    "fallidos": "Fallidos", "respuestas": "Respuestas", "error_code": "Código de error",
    "error_msg": "Mensaje de error", "cantidad": "Cantidad", "telefono": "Teléfono", "respuesta": "Respuesta",
    "estado": "Estado", "despachado_en": "Despachado", "enviado_en": "Enviado", "entregado_en": "Entregado",
    "leido_en": "Leído", "difusion": "Campaña", "partes": "Lotes y pruebas",
    "mensajes_lote": "Mensajes de lote", "pruebas": "Pruebas", "mensajes_prueba": "Mensajes de prueba",
}
COLUMNAS_ANCHAS = {"Campaña", "Respuesta", "Mensaje de error"}

# "Nombre 11 11 26 . Lote 001" y "Nombre 09 11 26 . Prueba 001" son la misma campaña:
# se ignoran el último tramo después de " . " y la fecha al final del nombre.
_SEPARADOR = re.compile(r"\s*\.\s+")  # " . " o ". " (a veces falta el espacio antes del punto)
_FECHA_FINAL = re.compile(r"\s+\d{1,2}[\s/-]+\d{1,2}[\s/-]+\d{2,4}$")


def presentar(tabla: pd.DataFrame) -> pd.DataFrame:
    """Encabezados legibles para pantalla, Excel y PDF."""
    texto = tabla.select_dtypes(include=["object", "str"]).columns
    return tabla.assign(**{c: tabla[c].where(tabla[c].notna(), "—") for c in texto}).rename(columns=ETIQUETAS)


def kpis(df: pd.DataFrame) -> dict:
    total = len(df)
    valores = {
        "Total mensajes": total,
        "Enviados": int(df["enviado_en"].notna().sum()),
        "Entregados": int(df["entregado_en"].notna().sum()),
        "Leídos": int(df["leido_en"].notna().sum()),
        "Fallidos": int((df["estado"] == "Fallido").sum()),
        "Respuestas": int((df["respuesta"] != "").sum()),
        "Opt-outs": int(df["opt_out_en"].notna().sum()),
    }
    return {k: (v, v / total if total and k != "Total mensajes" else None) for k, v in valores.items()}


def tabla_kpis(df) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Indicador": k, "Cantidad": v, "% del total": f"{p:.1%}" if p is not None else ""}
         for k, (v, p) in kpis(df).items()]
    )


def difusion(campana: str) -> str:
    """Nombre de la campaña sin su último tramo (lote, prueba, etc.) ni la fecha final."""
    tramos = _SEPARADOR.split(campana.strip())
    base = " . ".join(tramos[:-1]) if len(tramos) > 1 else tramos[0]
    return _FECHA_FINAL.sub("", base).strip() or base


def agrupar_campanas(nombres) -> dict[str, str]:
    """{nombre de cada envío: nombre de su campaña}. El nombre se toma del lote si lo hay."""
    grupos: dict[str, list[str]] = {}
    for n in nombres:
        clave = " ".join(difusion(n).casefold().split())
        grupos.setdefault(clave, []).append(n)
    resultado = {}
    for envios in grupos.values():
        lotes = [n for n in envios if re.search(r"\blote", n, re.IGNORECASE)]
        nombre = difusion((lotes or envios)[0])
        resultado.update({n: nombre for n in envios})
    return resultado


def renombrar_envio(envio: str, campana_nueva: str) -> str:
    """Cambia el nombre de la campaña y conserva el final del envío (". Lote 001", ". Prueba 003")."""
    tramos = _SEPARADOR.split(envio.strip())
    return f"{campana_nueva.strip()} . {tramos[-1]}" if len(tramos) > 1 else campana_nueva.strip()


def _resumen(df, claves) -> pd.DataFrame:
    t = df.groupby(claves, dropna=False, sort=False).agg(
        primer_envio=("despachado_en", "min"),
        total=("id", "count"),
        enviados=("enviado_en", "count"),
        entregados=("entregado_en", "count"),
        leidos=("leido_en", "count"),
        fallidos=("estado", lambda s: (s == "Fallido").sum()),
        respuestas=("respuesta", lambda s: (s != "").sum()),
    ).reset_index()
    t["% entrega"] = (t["entregados"] / t["total"]).map("{:.1%}".format)
    t["% lectura"] = (t["leidos"] / t["total"]).map("{:.1%}".format)
    return t.sort_values("primer_envio", ascending=False)


def por_campana(df) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    return _resumen(df, ["empresa", "plataforma", "campana", "categoria", "solicitado_por", "fecha_solicitud"])


def con_difusion(df) -> pd.DataFrame:
    """Agrega la columna difusion (campaña completa); las mayúsculas no separan campañas.

    Los datos de la campaña (nombre, categoría, solicitante) se toman del lote, o de la parte
    más reciente si no hay lote. Si la columna ya está calculada, no se vuelve a calcular.
    """
    if "difusion" in df.columns:
        return df
    base = df["campana"].map(difusion)
    clave = base.str.casefold().str.split().str.join(" ")
    es_lote = df["campana"].str.contains(r"\blote", case=False)
    orden = pd.DataFrame({"lote": es_lote, "envio": df["despachado_en"]}).sort_values(
        ["lote", "envio"], ascending=False, kind="stable").index
    grupo = [df["empresa"], df["plataforma"], clave]
    d = df.assign(difusion=base)
    for col in ["difusion", "categoria", "solicitado_por", "fecha_solicitud"]:
        d[col] = d.loc[orden, col].groupby([g.loc[orden] for g in grupo], dropna=False).transform("first")
    return d


def por_difusion(df) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    d = con_difusion(df)
    claves = ["empresa", "plataforma", "difusion", "categoria", "solicitado_por", "fecha_solicitud"]
    t = _resumen(d, claves)
    partes = d.groupby(claves, dropna=False)["campana"].nunique().rename("partes").reset_index()
    t = t.merge(partes, on=claves)
    return t[[*claves, "partes", *[c for c in t.columns if c not in claves and c != "partes"]]]


def por_categoria(df) -> pd.DataFrame:
    """Una fila por categoría de Meta (UTILITY, MARKETING): difusiones, mensajes, entregados y leídos."""
    import db

    d = con_difusion(df)
    t = d.groupby("categoria").agg(difusiones=("difusion", "nunique"), mensajes=("id", "count"),
                                   entregados=("entregado_en", "count"), leidos=("leido_en", "count"))
    t = t.reindex([*db.CATEGORIAS, *[c for c in t.index if c not in db.CATEGORIAS]], fill_value=0)
    t = t.rename_axis("categoria").reset_index()
    t["% lectura"] = (t["leidos"] / t["mensajes"].where(t["mensajes"] > 0)).map(
        lambda x: f"{x:.1%}" if pd.notna(x) else "")
    return t


def errores(df) -> pd.DataFrame:
    e = df[df["error_code"].notna()]
    if e.empty:
        return pd.DataFrame(columns=["error_code", "error_msg", "cantidad"])
    return (e.groupby(["error_code", "error_msg"], dropna=False).size()
            .reset_index(name="cantidad").sort_values("cantidad", ascending=False))


def respuestas(df) -> pd.DataFrame:
    """Lista legible de quienes respondieron (sin JSON): tipo, calificación, motivos y comentario."""
    import respuestas as R

    import db

    return R.lista_legible(R.analizar(con_difusion(df), db.significados(db.conectar())))


def _es_prueba(envio: str) -> bool:
    return "prueba" in _SEPARADOR.split(envio.strip())[-1].casefold()


def informe_campanas(df) -> pd.DataFrame:
    """Una fila por campaña: datos generales, volumen de lote y de pruebas, y resultados."""
    if df.empty:
        return pd.DataFrame()
    d = con_difusion(df)
    d = d.assign(_prueba=d["campana"].map(_es_prueba))
    claves = ["empresa", "difusion", "categoria", "solicitado_por", "fecha_solicitud"]
    t = _resumen(d, claves)
    extra = d.groupby(claves, dropna=False).apply(
        lambda g: pd.Series({
            "mensajes_lote": int((~g["_prueba"]).sum()),
            "pruebas": int(g.loc[g["_prueba"], "campana"].nunique()),
            "mensajes_prueba": int(g["_prueba"].sum()),
        }), include_groups=False).reset_index()
    t = t.merge(extra, on=claves)
    t["% respuesta"] = (t["respuestas"] / t["total"]).map("{:.1%}".format)
    return t[[*claves, "primer_envio", "total", "mensajes_lote", "pruebas", "mensajes_prueba",
              "entregados", "leidos", "fallidos", "respuestas", "% entrega", "% lectura", "% respuesta"]]


# Tablas generales del informe. Errores y Respuestas van por campaña (gráficos con 1 campaña, tablas con varias).
TABLAS = ["Resumen general", "Por campaña"]


def secciones(df, elegidas) -> dict[str, pd.DataFrame]:
    fuentes = {"Resumen general": tabla_kpis, "Por campaña": informe_campanas}
    return {s: presentar(fuentes[s](df)) for s in TABLAS if s in elegidas}


def campanas_de(df) -> list[tuple[str, str]]:
    """[(empresa, campaña)] presentes en los mensajes, de la que tiene más mensajes a la que tiene menos."""
    d = con_difusion(df)
    return list(d.groupby(["empresa", "difusion"]).size().sort_values(ascending=False).index)


def _significados() -> dict:
    import db

    return db.significados(db.conectar())


def por_campana_informe(df, elegidas) -> list[dict]:
    """Por cada campaña: su encabezado, su tabla de respuestas y su tabla de errores (informe de varias campañas)."""
    import respuestas as R

    d = con_difusion(df)
    sig = _significados()
    a = R.analizar(d, sig)
    salida = []
    for empresa, campana in campanas_de(d):
        dc = d[(d["empresa"] == empresa) & (d["difusion"] == campana)]
        bloque = {"empresa": empresa, "campana": campana, "mensajes": len(dc),
                  "respondieron": int((dc["respuesta"] != "").sum())}
        if "Respuestas de clientes" in elegidas:
            conf = sig.get((empresa, " ".join(campana.casefold().split())), {})
            bloque["respuestas"] = R.tabla_campana(a, empresa, campana, conf)
        if "Errores" in elegidas:
            bloque["errores"] = presentar(errores(dc))
        salida.append(bloque)
    return salida


def _imagenes(df, elegidas=None) -> list:
    """[(Grafico, png)] solo cuando el informe es de UNA campaña; con varias no hay gráficos."""
    import graficos

    if df.empty or len(campanas_de(df)) != 1:
        return []
    return [(g, graficos.png(g.fig)) for g in graficos.para_campana(con_difusion(df), secciones=elegidas)]


def _anchos(hoja, maximo=60):
    for col in hoja.columns:
        ancho = max(len(str(c.value or "")) for c in col[:300])
        hoja.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), maximo)


def excel_bytes(df, elegidas, filtros: dict, imagenes=None) -> bytes:
    """Una campaña: Resumen, Gráficos y Quiénes respondieron.
    Varias: Resumen, Respuestas por campaña (una tabla por campaña) y Quiénes respondieron."""
    from openpyxl.drawing.image import Image
    from openpyxl.styles import Alignment, Font

    una = len(campanas_de(df)) == 1 if not df.empty else False
    imagenes = (_imagenes(df, elegidas) if imagenes is None else imagenes) if una else []
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        # Hoja 1: Resumen
        pd.DataFrame(list(filtros.items()), columns=["Filtro", "Valor"]).to_excel(
            xw, sheet_name="Resumen", index=False, startrow=2)
        hoja = xw.sheets["Resumen"]
        hoja.cell(1, 1, "Informe de campañas").font = Font(bold=True, size=14)
        fila = len(filtros) + 5
        for nombre, tabla in secciones(df, elegidas).items():
            hoja.cell(fila, 1, nombre).font = Font(bold=True, size=12)
            tabla.to_excel(xw, sheet_name="Resumen", index=False, startrow=fila)
            fila += len(tabla) + 4
        _anchos(hoja, 45)

        if una and imagenes:
            # Hoja 2 (una campaña): Gráficos
            g_hoja = xw.book.create_sheet("Gráficos")
            g_hoja.column_dimensions["A"].width = 160
            fila = 1
            for g, imagen in imagenes:
                g_hoja.cell(fila, 1, g.titulo).font = Font(bold=True, size=13)
                celda = g_hoja.cell(fila + 1, 1, g.explicacion)
                celda.alignment = Alignment(wrap_text=True, vertical="top")
                g_hoja.row_dimensions[fila + 1].height = 45
                img = Image(BytesIO(imagen))
                img.width, img.height = img.width * 0.75, img.height * 0.75
                g_hoja.add_image(img, f"A{fila + 2}")
                fila += 3 + int(img.height / 20) + 2
        elif not una and ({"Respuestas de clientes", "Errores"} & set(elegidas)):
            # Hoja 2 (varias campañas): una tabla de respuestas (y de errores) por campaña, sin gráficos.
            nombre_hoja = "Respuestas por campaña"
            pd.DataFrame().to_excel(xw, sheet_name=nombre_hoja, index=False)
            r_hoja = xw.sheets[nombre_hoja]
            fila = 0
            for b in por_campana_informe(df, elegidas):
                r_hoja.cell(fila + 1, 1, b["campana"]).font = Font(bold=True, size=13)
                r_hoja.cell(fila + 2, 1, f"{b['empresa']} · {b['mensajes']:,} mensajes · "
                                         f"{b['respondieron']:,} respondieron")
                fila += 3
                for clave, titulo in [("respuestas", "Respuestas"), ("errores", "Errores")]:
                    if clave not in b:
                        continue
                    r_hoja.cell(fila + 1, 1, titulo).font = Font(bold=True)
                    if b[clave].empty:
                        r_hoja.cell(fila + 2, 1, "Sin datos.")
                        fila += 3
                    else:
                        b[clave].to_excel(xw, sheet_name=nombre_hoja, index=False, startrow=fila + 1)
                        fila += len(b[clave]) + 4
                fila += 1
            _anchos(r_hoja, 50)

        # Hoja 3: Quiénes respondieron
        if "Respuestas de clientes" in elegidas:
            lista = respuestas(df)
            lista.to_excel(xw, sheet_name="Quiénes respondieron", index=False)
            q_hoja = xw.sheets["Quiénes respondieron"]
            q_hoja.freeze_panes = "A2"
            if len(lista):
                q_hoja.auto_filter.ref = q_hoja.dimensions
            _anchos(q_hoja)
    return buf.getvalue()


def _latin1(texto) -> str:
    """Las fuentes base del PDF solo cubren latin-1; emojis y similares se reemplazan."""
    if texto is None or (not isinstance(texto, str) and pd.isna(texto)):
        return ""
    if isinstance(texto, pd.Timestamp):
        texto = texto.strftime("%Y-%m-%d %H:%M")
    texto = str(texto).replace("…", "...").replace("«", '"').replace("»", '"').replace("·", "-").replace("→", "->")
    return texto.encode("latin-1", "replace").decode("latin-1")


def pdf_bytes(df, elegidas, filtros: dict, imagenes=None) -> bytes:
    """Una campaña: tablas y luego sus gráficos explicados y su tabla de respuestas.
    Varias: tablas generales y una sección por campaña con su tabla de respuestas y de errores."""
    from fpdf import FPDF

    una = len(campanas_de(df)) == 1 if not df.empty else False
    imagenes = (_imagenes(df, elegidas) if imagenes is None else imagenes) if una else []
    pdf = FPDF(orientation="L", format="A4")
    pdf.set_auto_page_break(True, margin=12)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    titulo = f"Informe de campaña: {campanas_de(df)[0][1]}" if una else "Informe de campañas"
    pdf.multi_cell(0, 8, _latin1(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", size=9)
    for k, v in filtros.items():
        pdf.cell(0, 5, _latin1(f"{k}: {v}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    def tabla_pdf(nombre, tabla, nivel=12):
        pdf.set_font("Helvetica", "B", nivel)
        pdf.cell(0, 8, _latin1(nombre), new_x="LMARGIN", new_y="NEXT")
        if tabla.empty:
            pdf.set_font("Helvetica", size=9)
            pdf.cell(0, 6, "Sin datos para los filtros elegidos.", new_x="LMARGIN", new_y="NEXT")
            return
        pdf.set_font("Helvetica", size=7)
        anchos = [5 if c in COLUMNAS_ANCHAS else 3 if c in ("Respuesta", "Valor original") else
                  1.4 if c in ("Solicitado por", "Primer envío", "Empresa") else 1 for c in tabla.columns]
        with pdf.table(text_align="LEFT", line_height=4.2, col_widths=anchos) as t:
            fila = t.row()
            for c in tabla.columns:
                fila.cell(_latin1(c))
            for registro in tabla.itertuples(index=False):
                fila = t.row()
                for v in registro:
                    fila.cell(_latin1(v))
        pdf.ln(4)

    for nombre, tabla in secciones(df, elegidas).items():
        tabla_pdf(nombre, tabla)

    if una:
        if imagenes:
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 9, _latin1("Gráficos"), new_x="LMARGIN", new_y="NEXT")
            for g, imagen in imagenes:
                alto = pdf.epw * g.fig.layout.height / 1400
                if pdf.get_y() + 20 + min(alto, pdf.eph) > pdf.page_break_trigger:
                    pdf.add_page()
                pdf.set_font("Helvetica", "B", 12)
                pdf.cell(0, 7, _latin1(g.titulo), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", size=9)
                pdf.multi_cell(0, 4.6, _latin1(g.explicacion), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(1)
                ancho = pdf.epw if alto <= pdf.eph - 25 else pdf.epw * (pdf.eph - 25) / alto
                pdf.image(BytesIO(imagen), w=ancho)
                pdf.ln(5)
        if "Respuestas de clientes" in elegidas:
            b = por_campana_informe(df, elegidas)[0]
            pdf.add_page()
            tabla_pdf("Respuestas de la campaña", b["respuestas"])
    else:
        for b in por_campana_informe(df, elegidas):
            if not ({"respuestas", "errores"} & set(b)):
                break
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 7, _latin1(b["campana"]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", size=9)
            pdf.cell(0, 5, _latin1(f"{b['empresa']} · {b['mensajes']:,} mensajes · {b['respondieron']:,} respondieron"),
                     new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)
            if "respuestas" in b:
                tabla_pdf("Respuestas", b["respuestas"], 11)
            if "errores" in b:
                tabla_pdf("Errores", b["errores"], 11)
    return bytes(pdf.output())
