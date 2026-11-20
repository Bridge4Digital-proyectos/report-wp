"""Cliente de la Reports API de Connectly (https://docs.connectly.ai/analytics/reports-api).

GET /v1/businesses/{businessId}/reporting/reports?type=... con el encabezado X-API-Key devuelve, por cada
reporte configurado, su última ejecución con un enlace firmado y temporal al CSV.
"""
from io import BytesIO

import requests

BASE = "https://api.connectly.ai/v1"
TIEMPO = 60


class ErrorConnectly(Exception):
    pass


def _get(url, **kwargs):
    try:
        r = requests.get(url, timeout=TIEMPO, **kwargs)
    except requests.exceptions.SSLError as e:
        # No se desactiva la verificación SSL: suele ser el filtro web de la red interceptando la conexión.
        raise ErrorConnectly(f"Conexión segura rechazada ({e}). ¿Un filtro de red bloquea api.connectly.ai?") from e
    except requests.exceptions.RequestException as e:
        raise ErrorConnectly(f"No se pudo conectar con Connectly: {e}") from e
    if r.status_code in (401, 403):
        raise ErrorConnectly(f"Connectly rechazó la API key o el Business ID (HTTP {r.status_code}).")
    if r.status_code >= 400:
        raise ErrorConnectly(f"Connectly respondió HTTP {r.status_code}: {r.text[:300]}")
    return r


def reportes(business_id: str, api_key: str, tipo: str | None = None) -> list[dict]:
    """Reportes configurados del negocio, cada uno con su última ejecución (`lastRun`)."""
    params = {"type": tipo} if tipo else None
    r = _get(f"{BASE}/businesses/{business_id}/reporting/reports", headers={"X-API-Key": api_key}, params=params)
    try:
        return r.json().get("data", [])
    except ValueError as e:
        raise ErrorConnectly("Connectly devolvió una respuesta que no es JSON.") from e


def ultima_ejecucion(business_id: str, api_key: str, tipo: str = "", prefijo: str = "") -> dict | None:
    """La ejecución completada más reciente de los reportes de ese tipo cuyo nombre empieza con `prefijo`.

    Devuelve {id, createdAt, url, nombre} o None. Los reportes diarios llevan la fecha al final del nombre
    ("..._diario_-_2026-11-19"), así que el más reciente es el de nombre mayor.
    """
    mejores = []
    for rep in reportes(business_id, api_key, tipo or None):
        run = rep.get("lastRun") or {}
        resultado = run.get("result") or {}
        nombre = rep.get("name") or ""
        if tipo and rep.get("type") != tipo:
            continue
        if prefijo and not nombre.startswith(prefijo):
            continue
        if run.get("status") == "completed" and resultado.get("url"):
            mejores.append({"id": run.get("id") or f"{rep.get('id')}:{resultado.get('createdAt')}",
                            "createdAt": resultado.get("createdAt"), "url": resultado["url"], "nombre": nombre})
    return max(mejores, key=lambda e: (e["nombre"], e["createdAt"] or "")) if mejores else None


def descargar(url: str) -> BytesIO:
    """Descarga el CSV del enlace firmado (sin la API key: el enlace ya trae su firma)."""
    contenido = BytesIO(_get(url).content)
    contenido.name = "connectly_api.csv"
    return contenido
