"""Guardar reportes sin duplicar: lo nuevo completa lo que ya había y un campo vacío nunca borra un dato.

Es la misma lógica de la app anterior (db.guardar_carga), sobre el ORM de Django y con inserciones en bloque.
"""
from datetime import datetime

import pandas as pd
from django.db import transaction

from nucleo.models import Campana, Carga, Empresa, Mensaje, categoria_normal
from nucleo.servicios import datos
from nucleo.servicios.importacion import calcular_estado

FECHAS = ["despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en"]
CAMPOS_MEZCLA = ["telefono", "despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en",
                 "error_code", "error_msg", "respuesta", "plantilla"]
CAMPOS_GUARDADOS = [*CAMPOS_MEZCLA, "estado", "clics_boton", "clics_link"]
DELTAS = {"entregados": "entregado_en", "leidos": "leido_en", "respuestas": "respuesta", "opt_outs": "opt_out_en"}


def _vacio(v) -> bool:
    return v is None or v is pd.NaT or (isinstance(v, float) and pd.isna(v)) or v == ""


def _normal(v):
    """Valor comparable entre lo que viene del archivo y lo guardado."""
    if _vacio(v):
        return None
    if isinstance(v, datetime):
        return pd.Timestamp(v).isoformat()
    return str(int(v)) if isinstance(v, (int, float)) else str(v)


def _fecha(v):
    """Texto de fecha del reporte -> datetime sin zona horaria (se conserva la hora tal como viene)."""
    if _vacio(v):
        return None
    try:
        t = pd.Timestamp(v)
    except (ValueError, TypeError):
        return None
    if pd.isna(t):
        return None
    if t.tzinfo is not None:
        t = t.tz_localize(None)
    return t.to_pydatetime()


def _claves(df: pd.DataFrame) -> pd.Series:
    """Clave de cada mensaje: id de sesión, o teléfono + despacho si no lo hay."""
    sid = df["session_id"].fillna("").astype(str)
    tiene_id = sid != ""
    return sid.where(tiene_id, df["telefono"].astype(str) + "|" + df["despachado_en"].astype(str))


def _fechas(serie: pd.Series) -> pd.Series:
    """Columna de fechas en texto -> datetime sin zona horaria (rápido; uno por uno solo si hay formatos mezclados)."""
    s = pd.to_datetime(serie.replace("", None), errors="coerce", format="ISO8601")
    if not pd.api.types.is_datetime64_any_dtype(s):  # zonas horarias distintas en la misma columna
        return serie.map(_fecha).astype(object)
    if s.dt.tz is not None:
        s = s.dt.tz_localize(None)
    return pd.Series([None if pd.isna(x) else x.to_pydatetime() for x in s], index=serie.index, dtype=object)


def _preparar(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["session_id"] = _claves(d)
    for col in FECHAS:
        d[col] = _fechas(d[col])
    return d


def _mezclar(nueva: dict, vieja: dict) -> dict:
    m = {c: vieja.get(c) if _vacio(nueva.get(c)) else nueva.get(c) for c in CAMPOS_MEZCLA}
    m = {c: None if _vacio(v) else v for c, v in m.items()}
    m["respuesta"] = m["respuesta"] or ""
    for c in ["clics_boton", "clics_link"]:
        m[c] = max(int(nueva.get(c) or 0), int(vieja.get(c) or 0))
    m["estado"] = calcular_estado(m["entregado_en"], m["leido_en"], m["enviado_en"], m["error_code"])
    return m


def _plan(df: pd.DataFrame, plataforma: str, empresa: Empresa | None):
    """[(campaña, clave, tipo, fila_mezclada, fila_anterior)] con tipo nueva / actualizada / sin_cambios."""
    df = _preparar(df)
    plan = []
    for nombre, grupo in df.groupby("campana", sort=False):
        existentes = {}
        if empresa is not None:
            previa = Campana.objects.filter(plataforma=plataforma, nombre=nombre, empresa=empresa).first()
            if previa:
                existentes = {r["session_id"]: r for r in
                              Mensaje.objects.filter(campana=previa).values("id", "session_id", *CAMPOS_GUARDADOS)}
        for fila in grupo.to_dict("records"):
            vieja = existentes.get(fila["session_id"])
            mezcla = _mezclar(fila, vieja or {})
            if vieja is None:
                tipo = "nueva"
            elif any(_normal(mezcla[c]) != _normal(vieja.get(c)) for c in mezcla):
                tipo = "actualizada"
            else:
                tipo = "sin_cambios"
            plan.append((nombre, fila["session_id"], tipo, mezcla, vieja or {}))
    return plan


def comparar(df: pd.DataFrame, plataforma: str, empresa: Empresa | None) -> pd.DataFrame:
    """Qué aportaría el archivo frente a lo ya guardado, por campaña. Solo lectura."""
    filas = []
    for nombre, _, tipo, mezcla, vieja in _plan(df, plataforma, empresa):
        f = {"campana": nombre, "mensajes": 1, "nuevas": int(tipo == "nueva"),
             "actualizadas": int(tipo == "actualizada"), "sin_cambios": int(tipo == "sin_cambios")}
        for nombre_delta, col in DELTAS.items():
            f[nombre_delta] = int(not _vacio(mezcla[col])) - int(not _vacio(vieja.get(col)))
        f["fallidos_antes"] = int(vieja.get("estado") == "Fallido")
        f["fallidos_despues"] = int(mezcla["estado"] == "Fallido")
        filas.append(f)
    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas).groupby("campana", sort=False).sum().reset_index()


def ultima_carga(archivo: str, empresa: Empresa) -> datetime | None:
    c = Carga.objects.filter(archivo=archivo, empresa=empresa).order_by("-fecha_carga").first()
    return c.fecha_carga if c else None


def guardar(df: pd.DataFrame, plataforma: str, empresa: Empresa, archivo: str, datos_campanas: dict | None = None,
            origen: str = "manual", usuario: str = "") -> tuple[int, int, int]:
    """Guarda el reporte quedándose con lo más nuevo. Devuelve (nuevas, actualizadas, sin_cambios).

    datos_campanas: {nombre del envío: {categoria, solicitado_por, fecha_solicitud}}. Si no se indica, una
    campaña que ya existía conserva sus datos y una nueva queda UTILITY (o la categoría del archivo).
    """
    datos_campanas = datos_campanas or {}
    with transaction.atomic():
        ids = {}
        for nombre in df["campana"].unique():
            info = datos_campanas.get(nombre)
            campana, creada = Campana.objects.get_or_create(plataforma=plataforma, nombre=nombre, empresa=empresa)
            if creada and not info:
                cat = df.loc[df["campana"] == nombre, "categoria_plantilla"].dropna() \
                    if "categoria_plantilla" in df.columns else pd.Series(dtype=str)
                info = {"categoria": cat.iloc[0] if not cat.empty else "UTILITY"}
            if info:
                campana.categoria = categoria_normal(info.get("categoria") or campana.categoria)
                if "solicitado_por" in info:
                    campana.solicitado_por = info.get("solicitado_por") or None
                if "fecha_solicitud" in info:
                    campana.fecha_solicitud = info.get("fecha_solicitud") or None
                campana.save()
            ids[nombre] = campana.id

        plan = _plan(df, plataforma, empresa)
        nuevos, cambiados = [], []
        for nombre, clave, tipo, mezcla, vieja in plan:
            if tipo == "nueva":
                nuevos.append(Mensaje(campana_id=ids[nombre], session_id=clave, **mezcla))
            elif tipo == "actualizada":
                cambiados.append(Mensaje(id=vieja["id"], campana_id=ids[nombre], session_id=clave, **mezcla))
        Mensaje.objects.bulk_create(nuevos, batch_size=2000, ignore_conflicts=True)
        Mensaje.objects.bulk_update(cambiados, CAMPOS_GUARDADOS, batch_size=2000)

        cuenta = {t: sum(1 for p in plan if p[2] == t) for t in ["nueva", "actualizada", "sin_cambios"]}
        Carga.objects.create(archivo=archivo, plataforma=plataforma, empresa=empresa, fecha_carga=datetime.now(),
                             origen=origen, usuario=usuario, filas_nuevas=cuenta["nueva"],
                             filas_actualizadas=cuenta["actualizada"], filas_duplicadas=cuenta["sin_cambios"])
        datos.cambiaron()
    return cuenta["nueva"], cuenta["actualizada"], cuenta["sin_cambios"]
