"""Importador del reporte "Detalle de Difusiones" de S1 (Excel o CSV).

Las columnas se buscan por nombre (sin tildes ni mayúsculas), así que sirve para el reporte de
cualquier empresa aunque cambie el orden de las columnas.
"""
import re
import unicodedata

import pandas as pd

from importers import calcular_estado, leer_tabla

LISTO = True

REQUERIDAS = ["difusion", "destino", "fecha programada", "fecha de envio", "estado de envio",
              "estado de entrega", "fecha de entrega"]
OPCIONALES = ["caso id", "plantilla", "codigo de error", "mensaje de error"]

# "terbocyl_dext_03112026_lote1" -> ("terbocyl_dext_03112026", "lote1")
_SUFIJO = re.compile(r"^(.*?)[\s_-]*((?:lote|prueba)\s*\d*)\s*$", re.IGNORECASE)


def _clave(columna: str) -> str:
    t = unicodedata.normalize("NFD", str(columna))
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return " ".join(t.casefold().replace("�", "").split())


def nombre_envio(difusion: str) -> str:
    """Lleva el nombre de S1 al formato del proyecto: "campaña . lote1" / "campaña . Prueba"."""
    texto = " ".join(str(difusion).split())
    m = _SUFIJO.match(texto)
    if not m or not m.group(1):
        return texto
    return f"{m.group(1)} . {m.group(2)}"


def _columnas(df: pd.DataFrame) -> dict:
    claves = {_clave(c): c for c in df.columns}
    # Si la codificación rompió una tilde ("Env�o" -> "envo"), se compara también sin vocales acentuables.
    flojas = {re.sub(r"[aeiou]", "", k): c for k, c in claves.items()}
    encontradas = {}
    for nombre in REQUERIDAS + OPCIONALES:
        col = claves.get(nombre) or flojas.get(re.sub(r"[aeiou]", "", nombre))
        if col is not None:
            encontradas[nombre] = col
    return encontradas


def parse(archivo) -> pd.DataFrame:
    df = leer_tabla(archivo)
    col = _columnas(df)
    faltan = [c for c in REQUERIDAS if c not in col]
    if faltan:
        raise ValueError("El archivo no parece un \"Detalle de Difusiones\" de S1. Faltan columnas: "
                         + ", ".join(faltan))

    def v(fila, nombre):
        c = col.get(nombre)
        return str(fila[c]).strip() if c is not None else ""

    filas = []
    for fila in df.to_dict("records"):
        destino = v(fila, "destino")
        if not destino:
            continue
        envio_ok = "FAIL" not in v(fila, "estado de envio").upper()
        entrega = v(fila, "estado de entrega").upper()
        fecha_entrega = v(fila, "fecha de entrega") or None
        entregado = fecha_entrega if envio_ok and ("READ" in entrega or "DELIVERED" in entrega) else None
        leido = fecha_entrega if envio_ok and "READ" in entrega else None

        error_code = error_msg = None
        if not envio_ok or "FAIL" in entrega:
            codigo = v(fila, "codigo de error")
            error_code = codigo if codigo not in ("", "0") else (
                "S1_FALLA_ENVIO" if not envio_ok else "S1_FALLA_ENTREGA")
            error_msg = v(fila, "mensaje de error") or None

        caso = v(fila, "caso id")
        caso = caso[:-2] if caso.endswith(".0") else caso
        enviado = (v(fila, "fecha de envio") or None) if envio_ok else None
        filas.append({
            "campana": nombre_envio(v(fila, "difusion")),
            "telefono": destino[:-2] if destino.endswith(".0") else destino,
            "session_id": None,
            "despachado_en": v(fila, "fecha programada") or v(fila, "fecha de envio") or None,
            "enviado_en": enviado,
            "entregado_en": entregado,
            "leido_en": leido,
            "opt_out_en": None,
            "error_code": error_code,
            "error_msg": error_msg,
            "estado": calcular_estado(entregado, leido, enviado, error_code),
            "respuesta": f"Abrió caso N° {caso}" if caso else "",
            "clics_boton": 0,
            "clics_link": 0,
            "plantilla": v(fila, "plantilla") or None,
            "categoria_plantilla": None,
        })
    if not filas:
        raise ValueError("El archivo de S1 no tiene mensajes con destino.")
    return pd.DataFrame(filas)
