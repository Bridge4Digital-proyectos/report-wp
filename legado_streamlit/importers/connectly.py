"""Importador del CSV de difusiones exportado desde Connectly."""
import json

import pandas as pd

from importers import calcular_estado, leer_tabla

COLUMNAS_REQUERIDAS = [
    "customer_external_id", "campaign_name", "cnt_session_id", "dispatched_at",
    "sent_at", "delivered_at", "read_at", "error_code", "error_msg", "templates", "responses",
]


def _json(valor):
    if not valor:
        return None
    try:
        return json.loads(valor)
    except (ValueError, TypeError):
        return None


def _clics(valor) -> int:
    """Formato no visto aún en los archivos: acepta número, lista JSON o texto."""
    if not valor:
        return 0
    if str(valor).isdigit():
        return int(valor)
    datos = _json(valor)
    if isinstance(datos, (list, dict)):
        return len(datos)
    return 1


def _respuesta(fila) -> str:
    if fila.get("responses"):
        return fila["responses"]
    salida = _json(fila.get("output_variables"))
    if isinstance(salida, dict):
        return str(salida.get("respuesta_cliente") or "")
    return ""


LISTO = True


def parse(archivo) -> pd.DataFrame:
    df = leer_tabla(archivo)
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltan:
        raise ValueError(
            "El archivo no parece un reporte de Connectly. Faltan columnas: " + ", ".join(faltan)
        )

    filas = []
    for fila in df.to_dict("records"):
        plantillas = _json(fila.get("templates")) or []
        plantilla = plantillas[0] if plantillas else {}
        filas.append({
            "campana": fila["campaign_name"].strip(),
            "telefono": fila["customer_external_id"],
            "session_id": fila["cnt_session_id"] or None,
            "despachado_en": fila["dispatched_at"] or None,
            "enviado_en": fila["sent_at"] or None,
            "entregado_en": fila["delivered_at"] or None,
            "leido_en": fila["read_at"] or None,
            "opt_out_en": fila.get("opt_out_at") or None,
            "error_code": fila["error_code"] or None,
            "error_msg": fila["error_msg"] or None,
            "estado": calcular_estado(
                fila["delivered_at"], fila["read_at"], fila["sent_at"], fila["error_code"]
            ),
            "respuesta": _respuesta(fila),
            "clics_boton": _clics(fila.get("button_clicks")),
            "clics_link": _clics(fila.get("link_clicks")),
            "plantilla": plantilla.get("name"),
            "categoria_plantilla": (plantilla.get("category") or "").upper() or None,
        })
    return pd.DataFrame(filas)
