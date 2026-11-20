"""Piezas comunes de los importadores (app connectly): cada uno convierte su archivo en filas normalizadas.

Columnas normalizadas que devuelve parse():
campana, telefono, session_id, despachado_en, enviado_en, entregado_en, leido_en,
opt_out_en, error_code, error_msg, estado, respuesta, clics_boton, clics_link,
plantilla, categoria_plantilla
"""

import pandas as pd

ESTADOS = ["Leído", "Entregado", "Enviado", "Pendiente", "Fallido"]


def leer_tabla(archivo) -> pd.DataFrame:
    """Lee un CSV o un Excel (primera hoja) como texto; los vacíos quedan como ""."""
    nombre = str(getattr(archivo, "name", archivo)).lower()
    if nombre.endswith((".xlsx", ".xls")):
        df = pd.read_excel(archivo, dtype=str).fillna("")
    else:
        df = pd.read_csv(archivo, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def calcular_estado(entregado, leido, enviado, error_code) -> str:
    """Un solo estado por mensaje, para que los conteos cuadren."""
    if error_code and not entregado:
        return "Fallido"
    if leido:
        return "Leído"
    if entregado:
        return "Entregado"
    if enviado:
        return "Enviado"
    return "Pendiente"


