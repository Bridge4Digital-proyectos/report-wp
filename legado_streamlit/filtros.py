"""Filtros de la barra lateral, compartidos por el dashboard y el informe.

La campaña no se filtra aquí: se elige en la tabla del Dashboard o en el selector del Informe."""
import pandas as pd
import streamlit as st

import db
import reports


def aplicar(df: pd.DataFrame, clave: str) -> tuple[pd.DataFrame, dict]:
    """Muestra los filtros y devuelve (mensajes filtrados, descripción de los filtros)."""
    df = reports.con_difusion(df)
    sb = st.sidebar
    sb.header("Filtros")

    # Nunca se mezclan empresas ni plataformas: siempre se trabaja con una empresa y una plataforma.
    empresa = sb.selectbox("Empresa", sorted(df["empresa"].unique()), key=f"{clave}_empresa_unica")
    df = df[df["empresa"] == empresa]
    plataformas = sorted(df["plataforma"].unique())
    plataforma = sb.selectbox("Plataforma", plataformas, key=f"{clave}_plataforma_unica",
                              disabled=len(plataformas) == 1,
                              help="Los reportes de cada plataforma se ven por separado.")
    df = df[df["plataforma"] == plataforma]
    elegido = {"Empresa": empresa, "Plataforma": plataforma}

    def multi(etiqueta, columna, opciones=None):
        opciones = opciones if opciones is not None else sorted(df[columna].dropna().unique())
        valores = sb.multiselect(etiqueta, opciones, key=f"{clave}_{columna}", placeholder="Todas")
        if valores:
            elegido[etiqueta] = ", ".join(map(str, valores))
        return valores

    df = df.assign(_mes=reports.etiqueta_mes(df["despachado_en"]).values)
    meses = multi("Mes", "_mes", reports.meses_ordenados(df["despachado_en"]))
    categorias = multi("Categoría Meta", "categoria", db.CATEGORIAS)
    solicitantes = multi("Solicitado por", "solicitado_por")

    fechas = df["despachado_en"].dropna()
    rango = None
    if not fechas.empty:
        minimo, maximo = fechas.min().date(), fechas.max().date()
        rango = sb.date_input("Fecha de envío", (minimo, maximo), min_value=minimo,
                              max_value=maximo, key=f"{clave}_fechas")
        if isinstance(rango, tuple) and len(rango) == 2 and rango != (minimo, maximo):
            elegido["Fecha de envío"] = f"{rango[0]} a {rango[1]}"

    m = pd.Series(True, index=df.index)
    for valores, columna in [(meses, "_mes"), (categorias, "categoria"), (solicitantes, "solicitado_por")]:
        if valores:
            m &= df[columna].isin(valores)
    if isinstance(rango, tuple) and len(rango) == 2:
        dia = df["despachado_en"].dt.date
        m &= (dia >= rango[0]) & (dia <= rango[1])

    return df[m].drop(columns="_mes"), elegido
