"""Lectura de la base para los análisis, con caché por proceso.

La caché se invalida con `Version` (sube con cada carga o edición), así todos los procesos del servidor
ven los cambios. Llamar a `cambiaron()` después de guardar cualquier dato.
"""
import threading

import pandas as pd
from django.db.models import Count, Max, Min

from nucleo.models import Campana, Empresa, Mensaje, Significado, Version
from nucleo.servicios import analisis
from nucleo.servicios import respuestas as R

_CACHE: dict = {}
_LOCK = threading.Lock()

CAMPOS = {
    "id": "id", "campana_id": "campana_id", "empresa": "campana__empresa__nombre",
    "plataforma": "campana__plataforma", "campana": "campana__nombre", "categoria": "campana__categoria",
    "solicitado_por": "campana__solicitado_por", "fecha_solicitud": "campana__fecha_solicitud",
    "telefono": "telefono", "session_id": "session_id", "despachado_en": "despachado_en",
    "enviado_en": "enviado_en", "entregado_en": "entregado_en", "leido_en": "leido_en", "opt_out_en": "opt_out_en",
    "error_code": "error_code", "error_msg": "error_msg", "estado": "estado", "respuesta": "respuesta",
    "clics_boton": "clics_boton", "clics_link": "clics_link", "plantilla": "plantilla",
}
FECHAS = ["despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en"]


def cambiaron():
    """Avisar que los datos cambiaron (cargas, ediciones, significados)."""
    Version.subir()


def _cacheado(nombre, fabricar):
    version = Version.actual()
    with _LOCK:
        guardado = _CACHE.get(nombre)
        if guardado and guardado[0] == version:
            return guardado[1]
    valor = fabricar()
    with _LOCK:
        _CACHE[nombre] = (version, valor)
    return valor


def mantener_caliente(cada: int = 60):
    """Hilo del servidor web: cuando cambian los datos (p. ej. la sincronización diaria) los vuelve a cargar en
    segundo plano, así nadie espera la carga completa al abrir el Dashboard."""
    import logging
    import time

    from django.db import close_old_connections

    log = logging.getLogger(__name__)

    def ciclo():
        while True:
            try:
                mensajes()
                significados()
            except Exception:  # noqa: BLE001 - nunca debe detener el servidor
                log.exception("No se pudo precargar los datos.")
            finally:
                close_old_connections()
            time.sleep(cada)

    threading.Thread(target=ciclo, name="precarga-datos", daemon=True).start()


def _leer_mensajes() -> pd.DataFrame:
    filas = Mensaje.objects.values_list(*CAMPOS.values())
    df = pd.DataFrame.from_records(list(filas), columns=list(CAMPOS))
    if df.empty:
        return df
    for col in FECHAS:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df["fecha_solicitud"] = pd.to_datetime(df["fecha_solicitud"], errors="coerce").dt.date
    df["respuesta"] = df["respuesta"].fillna("")
    return analisis.con_difusion(df)


def mensajes() -> pd.DataFrame:
    """Todos los mensajes con su empresa, campaña (envío) y difusión (campaña completa)."""
    return _cacheado("mensajes", _leer_mensajes)


def _leer_significados() -> dict:
    salida: dict = {}
    for empresa, difusion, valor, significado, sentido in Significado.objects.values_list(
            "empresa__nombre", "difusion", "valor", "significado", "sentido"):
        salida.setdefault((empresa, difusion), {})[valor] = (significado, sentido)
    return salida


def significados() -> dict:
    """{(empresa, campaña normalizada): {valor: (significado, sentido)}}."""
    return _cacheado("significados", _leer_significados)


def respuestas(df: pd.DataFrame) -> pd.DataFrame:
    """Respuestas interpretadas con los significados de cada campaña (solo filas con respuesta)."""
    cols = ["empresa", "difusion", "telefono", "leido_en", "despachado_en", "respuesta"]
    return R.analizar(df.loc[df["respuesta"].fillna("").str.strip() != "", cols], significados())


def normalizar(nombre: str) -> str:
    """Clave de campaña: sin mayúsculas ni espacios repetidos (igual que al agrupar campañas)."""
    return " ".join(str(nombre).casefold().split())


def campanas() -> pd.DataFrame:
    """Un renglón por envío (lote o prueba), con su cantidad de mensajes y su primer envío."""
    filas = (Campana.objects.values("id", "plataforma", "nombre", "categoria", "solicitado_por", "fecha_solicitud",
                                    "empresa__nombre")
             .annotate(n_mensajes=Count("mensajes"), primer_envio=Min("mensajes__despachado_en"))
             .order_by("-primer_envio"))
    df = pd.DataFrame(list(filas))
    if df.empty:
        return df
    return df.rename(columns={"nombre": "campana", "empresa__nombre": "empresa", "n_mensajes": "mensajes"})[
        ["id", "empresa", "plataforma", "campana", "categoria", "solicitado_por", "fecha_solicitud", "mensajes",
         "primer_envio"]]


def resumen_empresas() -> list[dict]:
    return list(Empresa.objects.annotate(envios=Count("campanas", distinct=True), mensajes=Count("campanas__mensajes"),
                                         ultimo_envio=Max("campanas__mensajes__despachado_en"))
                .values("id", "nombre", "envios", "mensajes", "ultimo_envio"))


def guardar_significados(empresa: str, difusion: str, filas):
    """filas: [(valor, significado, sentido)] de una campaña."""
    e, clave = Empresa.objects.get(nombre=empresa), normalizar(difusion)
    for valor, sig, sentido in filas:
        Significado.objects.update_or_create(empresa=e, difusion=clave, valor=valor,
                                             defaults={"significado": (sig or "").strip() or valor, "sentido": sentido})
    cambiaron()


def borrar_significados(empresa: str, difusion: str):
    Significado.objects.filter(empresa__nombre=empresa, difusion=normalizar(difusion)).delete()
    cambiaron()
