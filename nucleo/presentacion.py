"""DataFrames -> tablas para las plantillas (texto ya formateado, alineación de números)."""
from datetime import date, datetime

import numpy as np
import pandas as pd

from nucleo.servicios import analisis

VACIO = "—"


def _celda(v) -> tuple[str, bool]:
    """(texto, es_numero)."""
    if v is None or v is pd.NaT or (isinstance(v, float) and pd.isna(v)):
        return VACIO, False
    if isinstance(v, (bool, np.bool_)):
        return ("Sí" if v else "No"), False
    if isinstance(v, (int, np.integer)):
        return f"{int(v):,}", True
    if isinstance(v, (float, np.floating)):
        return (f"{int(v):,}" if float(v).is_integer() else f"{v:,.1f}"), True
    if isinstance(v, (pd.Timestamp, datetime)):
        return pd.Timestamp(v).strftime("%Y-%m-%d %H:%M"), False
    if isinstance(v, date):
        return v.isoformat(), False
    texto = str(v)
    if texto in ("None", "nan", "NaT", "", "<NA>"):
        return VACIO, False
    return texto, texto.endswith("%") and texto[:-1].replace(".", "").replace(",", "").isdigit()


def tabla(df: pd.DataFrame, presentar: bool = True, ocultar=(), enlaces=None, elegida=None) -> dict:
    """{'columnas': [(nombre, es_numero)], 'filas': [{'celdas': [(texto, es_numero)], 'url', 'activa'}]}.

    enlaces: función fila(dict) -> url para que cada fila sea clicable; elegida: fila(dict) -> bool.
    """
    if df is None or df.empty:
        return {"columnas": [], "filas": []}
    original = df.reset_index(drop=True)
    vista = analisis.presentar(original) if presentar else original
    visibles = [c for c in vista.columns if c not in ocultar]
    filas = []
    for i, r in enumerate(vista[visibles].itertuples(index=False, name=None)):
        datos = original.iloc[i].to_dict() if (enlaces or elegida) else {}
        filas.append({"celdas": [_celda(v) for v in r], "url": enlaces(datos) if enlaces else None,
                      "activa": bool(elegida and elegida(datos))})
    columnas = [(c, all(f["celdas"][j][1] or f["celdas"][j][0] == VACIO for f in filas))
                for j, c in enumerate(visibles)]
    return {"columnas": columnas, "filas": filas}
