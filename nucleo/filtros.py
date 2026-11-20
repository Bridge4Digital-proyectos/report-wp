"""Filtros compartidos por Dashboard e Informe (vienen en la URL, así cada vista se puede compartir/recargar).

Nunca se mezclan empresas ni plataformas: siempre hay UNA empresa y UNA plataforma elegidas.
"""
from datetime import date
from urllib.parse import urlencode

import pandas as pd

from nucleo.servicios import analisis


def _fecha(texto):
    try:
        return date.fromisoformat(texto) if texto else None
    except ValueError:
        return None


def aplicar(request, todo: pd.DataFrame):
    """Devuelve (mensajes filtrados, descripción de filtros para el informe, contexto para la plantilla)."""
    g = request.GET
    empresas = sorted(todo["empresa"].unique()) if not todo.empty else []
    empresa = g.get("empresa") or request.session.get("empresa")
    if empresa not in empresas:
        empresa = empresas[0] if empresas else None
    request.session["empresa"] = empresa
    df = todo[todo["empresa"] == empresa] if empresa else todo.iloc[0:0]

    plataformas = sorted(df["plataforma"].unique()) if not df.empty else []
    plataforma = g.get("plataforma") or request.session.get(f"plataforma_{empresa}")
    if plataforma not in plataformas:
        plataforma = plataformas[0] if plataformas else None
    request.session[f"plataforma_{empresa}"] = plataforma
    df = df[df["plataforma"] == plataforma] if plataforma else df

    elegido = {"Empresa": empresa or "—", "Plataforma": plataforma or "—"}
    mes = analisis.etiqueta_mes(df["despachado_en"]).values if not df.empty else []
    opciones_mes = analisis.meses_ordenados(df["despachado_en"]) if not df.empty else []
    solicitantes = sorted(df["solicitado_por"].dropna().unique()) if not df.empty else []

    meses = [m for m in g.getlist("mes") if m in opciones_mes]
    categorias = [c for c in g.getlist("categoria") if c in analisis.CATEGORIAS]
    quienes = [s for s in g.getlist("solicitado") if s in solicitantes]
    desde, hasta = _fecha(g.get("desde")), _fecha(g.get("hasta"))
    if desde and hasta and desde > hasta:
        desde, hasta = hasta, desde
    envios = df["despachado_en"].dropna() if not df.empty else pd.Series(dtype="datetime64[ns]")

    m = pd.Series(True, index=df.index)
    if meses:
        m &= pd.Series(mes, index=df.index).isin(meses)
        elegido["Mes"] = ", ".join(meses)
    if categorias:
        m &= df["categoria"].isin(categorias)
        elegido["Categoría Meta"] = ", ".join(categorias)
    if quienes:
        m &= df["solicitado_por"].isin(quienes)
        elegido["Solicitado por"] = ", ".join(quienes)
    if desde or hasta:
        dia = df["despachado_en"].dt.date
        if desde:
            m &= dia >= desde
        if hasta:
            m &= dia <= hasta
        elegido["Fecha de envío"] = f"{desde or '…'} a {hasta or '…'}"
    df = df[m]

    base = {"empresa": empresa or "", "plataforma": plataforma or "", "mes": meses, "categoria": categorias,
            "solicitado": quienes, "desde": desde.isoformat() if desde else "",
            "hasta": hasta.isoformat() if hasta else ""}
    ctx = {
        "empresas": empresas, "empresa": empresa, "plataformas": plataformas, "plataforma": plataforma,
        "opciones_mes": opciones_mes, "meses": meses, "opciones_categoria": analisis.CATEGORIAS,
        "categorias": categorias, "solicitantes": solicitantes, "quienes": quienes,
        "desde": desde.isoformat() if desde else "", "hasta": hasta.isoformat() if hasta else "",
        "fecha_min": envios.min().date().isoformat() if not envios.empty else "",
        "fecha_max": envios.max().date().isoformat() if not envios.empty else "",
        "filtros_extra": len(meses) + len(categorias) + len(quienes),
        "qs": urlencode(base, doseq=True),
    }
    return df, elegido, ctx
