"""Importador de reportes de Connectly.

Acepta los dos formatos de CSV:
- el que se descarga a mano desde la campaña (trae dispatched_at, templates, responses...);
- el del reporte programado de la API (campaign.daily.v1): 15 columnas, sin dispatched_at, templates ni
  responses. Ahí el despacho se toma de sent_at y la respuesta de output_variables.
"""
import json

import pandas as pd

from nucleo.models import EQUIVALENCIAS
from nucleo.servicios.importacion import calcular_estado, leer_tabla

COLUMNAS_REQUERIDAS = ["customer_external_id", "campaign_name", "cnt_session_id", "sent_at", "delivered_at",
                       "read_at", "error_code", "error_msg"]


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


def _plano(valor) -> str:
    """Un valor de output_variables como lo muestra Connectly en la columna `responses` del CSV manual:
    un objeto JSON sin listas se aplana a "clave: valor, clave: valor"; si trae listas, queda tal cual."""
    t = str(valor).strip()
    if t.startswith("{"):
        d = _json(t)
        if isinstance(d, dict) and not any(isinstance(x, (list, dict)) for x in d.values()):
            return ", ".join(f"{k}: {x}" for k, x in d.items())
    return t


def _respuesta(fila) -> str:
    """Respuesta del cliente. El CSV manual la trae en `responses`; el de la API, dentro de output_variables
    (respuesta_cliente, resp_flow, respuesta_encuesta...), y se une igual que Connectly: con " | "."""
    if fila.get("responses"):
        return fila["responses"]
    salida = _json(fila.get("output_variables"))
    if isinstance(salida, dict):
        return " | ".join(_plano(v) for v in salida.values() if str(v).strip())
    return ""


def formato(df: pd.DataFrame) -> str:
    return "manual" if "dispatched_at" in df.columns else "api"


def parse(archivo) -> pd.DataFrame:
    df = archivo if isinstance(archivo, pd.DataFrame) else leer_tabla(archivo)
    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltan:
        raise ValueError("El archivo no parece un reporte de Connectly. Faltan columnas: " + ", ".join(faltan))

    filas = []
    for fila in df.to_dict("records"):
        plantillas = _json(fila.get("templates")) or []
        plantilla = plantillas[0] if isinstance(plantillas, list) and plantillas else {}
        filas.append({
            "campana": str(fila["campaign_name"]).strip(),
            "telefono": fila["customer_external_id"],
            "session_id": fila["cnt_session_id"] or None,
            "despachado_en": fila.get("dispatched_at") or fila["sent_at"] or None,
            "enviado_en": fila["sent_at"] or None,
            "entregado_en": fila["delivered_at"] or None,
            "leido_en": fila["read_at"] or None,
            "opt_out_en": fila.get("opt_out_at") or None,
            "error_code": fila["error_code"] or None,
            "error_msg": fila["error_msg"] or None,
            "estado": calcular_estado(fila["delivered_at"], fila["read_at"], fila["sent_at"], fila["error_code"]),
            "respuesta": _respuesta(fila),
            "clics_boton": _clics(fila.get("button_clicks")),
            "clics_link": _clics(fila.get("link_clicks")),
            "plantilla": plantilla.get("name") if isinstance(plantilla, dict) else None,
            # MARKETING_LITE (Marketing Messages Lite de Meta) es MARKETING para Connectly.
            "categoria_plantilla": EQUIVALENCIAS.get(c := ((plantilla.get("category") if isinstance(plantilla, dict)
                                                             else "") or "").upper(), c) or None,
        })
    return pd.DataFrame(filas)
