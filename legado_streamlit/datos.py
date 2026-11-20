"""Lectura de la base con caché para las pantallas. Llamar a `limpiar()` después de guardar cambios."""
import pandas as pd
import streamlit as st

import db
import reports
import respuestas as R


@st.cache_data(ttl="10m", show_spinner=False)
def mensajes() -> pd.DataFrame:
    """Todos los mensajes, ya con la columna `difusion` (campaña agrupada)."""
    df = db.mensajes(db.conectar())
    return reports.con_difusion(df) if not df.empty else df


@st.cache_data(ttl="10m", show_spinner=False)
def significados() -> dict:
    """Significado y sentido de cada valor de respuesta, por campaña (lo que se edita en Campañas)."""
    return db.significados(db.conectar())


def _congelar(sig: dict) -> tuple:
    return tuple(sorted((k, tuple(sorted(v.items()))) for k, v in sig.items()))


@st.cache_data(ttl="10m", show_spinner=False, max_entries=20)
def _analizar(respondieron: pd.DataFrame, sig: tuple) -> pd.DataFrame:
    return R.analizar(respondieron, {k: dict(v) for k, v in sig})


def respuestas(df: pd.DataFrame) -> pd.DataFrame:
    """Respuestas interpretadas con los significados de cada campaña; la caché usa solo las filas con respuesta."""
    cols = ["empresa", "difusion", "telefono", "leido_en", "despachado_en", "respuesta"]
    return _analizar(df.loc[df["respuesta"].fillna("").str.strip() != "", cols], _congelar(significados()))


def limpiar():
    st.cache_data.clear()
