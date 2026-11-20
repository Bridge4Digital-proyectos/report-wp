"""Trae el último reporte de cada cuenta de Connectly y lo guarda sin duplicar.

El reporte que usan las cuentas de Tigo es "Campaign_Report_-_Ultimos_30_dias_diario_-_AAAA-MM-DD" (tipo
campaign.sessions.v1): Connectly lo genera cada día con TODAS las campañas de los últimos 30 días.
Cada día se vuelve a importar completo: lo ya guardado se actualiza y nunca se duplica.
"""
import logging
import threading
from datetime import datetime, timedelta

import pandas as pd
from django.db import close_old_connections

from connectly import api, importador
from connectly.models import CuentaConnectly, Sincronizacion
from nucleo.servicios import cargas

log = logging.getLogger(__name__)
MAX_DURACION = timedelta(minutes=30)  # una sincronización "en curso" más vieja que esto se considera caída


def _fecha(texto):
    try:
        t = pd.Timestamp(texto)
        return (t.tz_convert(None) if t.tzinfo else t).to_pydatetime(warn=False)
    except (ValueError, TypeError):
        return None


def en_curso(c: CuentaConnectly) -> bool:
    return Sincronizacion.objects.filter(cuenta=c, estado="en_curso", inicio__gte=datetime.now() - MAX_DURACION).exists()


def probar(c: CuentaConnectly) -> dict:
    """Solo lectura: qué reportes ve la API y qué traería el elegido (lee 2000 filas, no guarda nada)."""
    clave = c.api_key()
    reps = api.reportes(c.business_id, clave)
    run = api.ultima_ejecucion(c.business_id, clave, c.tipo_reporte, c.nombre_reporte)
    resumen = {"reportes_en_la_cuenta": len(reps),
               "tipos": sorted({r.get("type") for r in reps}),
               "elegido": {k: run[k] for k in ("nombre", "id", "createdAt")} if run else None}
    if run:
        crudo = pd.read_csv(api.descargar(run["url"]), dtype=str, keep_default_na=False, nrows=2000)
        df = importador.parse(crudo)
        resumen.update({"columnas": list(crudo.columns), "filas_muestra": len(df),
                        "con_respuesta_muestra": int((df["respuesta"] != "").sum()) if len(df) else 0,
                        "campanas_muestra": sorted(df["campana"].unique())[:10] if len(df) else []})
    return resumen


def cuenta(c: CuentaConnectly, origen: str = "programada") -> Sincronizacion:
    """Sincroniza una cuenta y deja el resultado en el registro de sincronizaciones."""
    if en_curso(c):
        return Sincronizacion.objects.create(cuenta=c, inicio=datetime.now(), fin=datetime.now(), estado="sin_novedad",
                                             origen=origen, detalle="Ya hay una sincronización en curso.")
    s = Sincronizacion.objects.create(cuenta=c, inicio=datetime.now(), estado="en_curso", origen=origen,
                                      detalle="Descargando el reporte de Connectly…")
    try:
        clave = c.api_key()
        run = api.ultima_ejecucion(c.business_id, clave, c.tipo_reporte, c.nombre_reporte)
        if run is None:
            s.estado = "sin_novedad"
            s.detalle = (f"Connectly no tiene un reporte completado «{c.nombre_reporte or '(cualquiera)'}» "
                         f"del tipo {c.tipo_reporte or '(cualquiera)'}.")
        elif Sincronizacion.objects.filter(cuenta=c, run_id=run["id"], estado="ok").exists():
            s.estado, s.run_id = "sin_novedad", run["id"]
            s.reporte_creado = _fecha(run["createdAt"])
            s.detalle = f"El último reporte ({run['nombre']}) ya estaba importado."
        else:
            df = importador.parse(api.descargar(run["url"]))
            s.detalle = f"Guardando {len(df):,} mensajes de {run['nombre']}…"
            s.save(update_fields=["detalle"])
            if df.empty:
                nuevos = actualizados = sin_cambios = 0
            else:
                nuevos, actualizados, sin_cambios = cargas.guardar(
                    df, "Connectly", c.empresa, f"API: {run['nombre']}", origen="api", usuario=f"sincronización {origen}")
            s.estado, s.run_id = "ok", run["id"]
            s.reporte_creado = _fecha(run["createdAt"])
            s.nuevos, s.actualizados, s.sin_cambios = nuevos, actualizados, sin_cambios
            s.detalle = (f"{run['nombre']}: {len(df):,} mensajes de {df['campana'].nunique() if len(df) else 0} "
                         f"envíos (lotes y pruebas).")
    except (api.ErrorConnectly, ValueError) as e:
        log.warning("Sincronización de %s falló: %s", c, e)
        s.estado, s.detalle = "error", str(e)
    except Exception as e:  # noqa: BLE001 - cualquier falla queda registrada, nunca "en curso" para siempre
        log.exception("Sincronización de %s falló", c)
        s.estado, s.detalle = "error", f"Error inesperado: {e}"
    s.fin = datetime.now()
    s.save()
    return s


def todas(origen: str = "programada") -> list[Sincronizacion]:
    return [cuenta(c, origen) for c in CuentaConnectly.objects.filter(activa=True).select_related("empresa")]


def en_segundo_plano(cuentas: list[CuentaConnectly], origen: str = "manual"):
    """Sincroniza sin hacer esperar a la página (un reporte de 30 días tarda unos minutos)."""
    def trabajo():
        try:
            for c in cuentas:
                cuenta(c, origen)
            from nucleo.servicios import datos
            datos.mensajes()  # deja lista la caché para la próxima visita al Dashboard
        finally:
            close_old_connections()

    threading.Thread(target=trabajo, name="sincronizar-connectly", daemon=True).start()
