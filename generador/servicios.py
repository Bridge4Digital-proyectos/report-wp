"""Indicadores del reporte HTML de una campaña, desde la base o desde un archivo CSV/Excel subido.

Lo recibe la empresa: sin costos y la plataforma se llama "Cocco" (nunca "Connectly").

Definiciones acordadas con el usuario:
- Gestión efectiva: el mensaje se ENVIÓ. Efectividad = enviados / mensajes de la base.
  Tasa de respuesta (aparte) = clientes que respondieron / enviados.
- Rechazado: la plataforma (WhatsApp/Meta) no aceptó el envío: hubo error y el mensaje nunca se envió.
  Fallido: se envió pero no se entregó (con error).
Los indicadores clave, el horario, el mapa de lectura y la calidad de la base salen de
nucleo.servicios.indicadores (los mismos que muestra el Dashboard).
"""
import base64
from datetime import datetime
from functools import lru_cache
from io import BytesIO
from pathlib import Path

import pandas as pd
from django.conf import settings

from nucleo.servicios import analisis, indicadores
from nucleo.servicios import respuestas as R
from nucleo.servicios.cargas import _fechas

MARCA = Path(settings.BASE_DIR) / "nucleo" / "static" / "nucleo" / "marca"
RECEPCION = ["Entregado", "Fallido", "Rechazado", "Sin confirmar"]
LECTURA = ["Leído", "No leído"]
MAX_TEXTO = 600  # caracteres de cada respuesta en la tabla de detalle


# ------------------------------------------------------------------ archivos subidos

def leer_archivo(ruta: str, nombre: str) -> tuple[str, pd.DataFrame]:
    """(plataforma, filas normalizadas) de un CSV (o Excel) de Connectly."""
    from connectly import importador as connectly

    contenido = BytesIO(Path(ruta).read_bytes())
    contenido.name = nombre
    return "Connectly", connectly.parse(contenido)


@lru_cache(maxsize=3)
def mensajes_de_archivo(ruta: str, nombre: str, empresa: str) -> tuple[str, pd.DataFrame]:
    """Mensajes del archivo con las mismas columnas que la base (para usar los mismos cálculos)."""
    plataforma, df = leer_archivo(ruta, nombre)
    df = df.copy()
    for col in ["despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en"]:
        df[col] = pd.to_datetime(_fechas(df[col]), errors="coerce")
    df["respuesta"] = df["respuesta"].fillna("")
    df = df.assign(id=range(len(df)), empresa=empresa, plataforma=plataforma,
                   categoria=df["categoria_plantilla"].fillna("").str.upper().replace("", "—"),
                   solicitado_por=None, fecha_solicitud=None)
    return plataforma, analisis.con_difusion(df)


# ------------------------------------------------------------------ indicadores

def _pct(n, total) -> str:
    return f"{n / total:.1%}".replace(".", ",") if total else "—"


def _n(x) -> str:
    return f"{int(x):,}".replace(",", ".")


def _barras(pares, total=None) -> list[dict]:
    """[(etiqueta, cantidad)] -> filas con % y ancho de barra (relativo al mayor)."""
    pares = [(e, int(c)) for e, c in pares]
    total = total if total is not None else sum(c for _, c in pares)
    mayor = max([c for _, c in pares] or [1]) or 1
    # El ancho va en CSS: siempre con punto decimal (la app está en español y Django escribiría "61,3").
    return [{"etiqueta": e, "n": _n(c), "pct": _pct(c, total), "ancho": f"{100 * c / mayor:.1f}"} for e, c in pares]


def _motivos(sub: pd.DataFrame, limite=8) -> list[dict]:
    if sub.empty:
        return []
    motivo = sub["error_msg"].fillna("").str.strip()
    motivo = motivo.where(motivo != "", "Código " + sub["error_code"].fillna("sin código").astype(str))
    conteo = motivo.value_counts()
    pares = list(conteo.head(limite).items())
    if len(conteo) > limite:
        pares.append((f"Otros motivos ({len(conteo) - limite})", int(conteo.iloc[limite:].sum())))
    return _barras(pares, total=len(sub))


def _parte(envio: str) -> str:
    tramos = analisis._SEPARADOR.split(str(envio).strip())
    return tramos[-1] if len(tramos) > 1 else str(envio)


def _mezcla(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _color_calor(t: float) -> str:
    """Escala de un solo tono de la marca: celeste muy claro -> azul vivo -> azul marino."""
    if t <= 0:
        return "#f3f6fd"
    return _mezcla("#c9d8fd", "#0f45f9", t / 0.55) if t <= 0.55 else _mezcla("#0f45f9", "#000062", (t - 0.55) / 0.45)


def _vista_mapa(m: dict) -> dict | None:
    if not m["total"]:
        return None
    raiz = m["maximo"] ** 0.5 or 1
    filas = []
    for etiqueta, valores in zip(m["filas"], m["valores"]):
        celdas = []
        for h, v in zip(m["horas"], valores):
            t = (v ** 0.5) / raiz if v else 0
            celdas.append({"color": _color_calor(t), "oscuro": t > 0.5,
                           "titulo": f"{etiqueta} · {h:02d}:00 — {_n(v)} lecturas ({_pct(v, m['total'])})"})
        filas.append({"etiqueta": etiqueta, "celdas": celdas})
    p = m["pico"]
    return {"filas": filas, "horas": [f"{h:02d}" for h in m["horas"]], "modo": m["modo"],
            "pico": f"{p['fila']} a las {p['hora']:02d}:00 ({_n(p['n'])} lecturas)",
            "hora_pico": f"{m['hora_pico']:02d}:00"}


def _vista_horario(h: dict) -> dict | None:
    if not h["total"]:
        return None
    mayor = max(h["entregas"]) or 1
    return {"columnas": [{"hora": f"{x:02d}", "n": _n(v), "pct": _pct(v, h["total"]), "alto": f"{100 * v / mayor:.1f}",
                          "pico": x == h["pico"]} for x, v in zip(h["horas"], h["entregas"])],
            "pico": f"{h['pico']:02d}:00", "pct_pico": _pct(h["entregas"][h["pico"]], h["total"]),
            "pct_1min": indicadores.pct(h["pct_1min"], ",")}


def calcular(df: pd.DataFrame, significados: dict | None = None, respuestas_cliente: bool = True) -> dict:
    """Todos los indicadores de UNA campaña (difusión completa: lote y pruebas).

    respuestas_cliente=False deja fuera la información de las respuestas (encuesta, clasificación y textos):
    el reporte solo dice si el cliente respondió o no (tasa de respuesta)."""
    total = len(df)
    contactos = df["telefono"].nunique()
    enviado = df["enviado_en"].notna()
    entregado = df["entregado_en"].notna()
    leido = df["leido_en"].notna()
    con_error = df["estado"] == "Fallido"
    rechazado = con_error & ~enviado
    fallido = con_error & enviado
    sin_confirmar = enviado & ~entregado & ~con_error
    respondio = df["respuesta"].fillna("").str.strip() != ""
    n = {k: int(v.sum()) for k, v in {"enviados": enviado, "entregados": entregado, "leidos": leido,
                                      "rechazados": rechazado, "fallidos": fallido, "sin_confirmar": sin_confirmar,
                                      "respondieron": respondio}.items()}

    kpis = [
        {"nombre": "Total de contactos", "valor": _n(contactos), "nota": f"{_n(total)} mensajes"},
        {"nombre": "Mensajes enviados", "valor": _n(n["enviados"]), "nota": _pct(n["enviados"], total) + " del total"},
        {"nombre": "Mensajes entregados", "valor": _n(n["entregados"]),
         "nota": _pct(n["entregados"], n["enviados"]) + " de los enviados"},
        {"nombre": "Mensajes leídos", "valor": _n(n["leidos"]),
         "nota": _pct(n["leidos"], n["entregados"]) + " de los entregados"},
        {"nombre": "Mensajes fallidos", "valor": _n(n["fallidos"]), "nota": _pct(n["fallidos"], total) + " del total"},
        {"nombre": "Mensajes rechazados", "valor": _n(n["rechazados"]),
         "nota": _pct(n["rechazados"], total) + " del total"},
    ]
    embudo = _barras([("Enviados", n["enviados"]), ("Entregados", n["entregados"]), ("Leídos", n["leidos"]),
                      ("Respondieron", n["respondieron"])], total=total)
    embudo[-1]["pct"] = _pct(n["respondieron"], n["enviados"]) + " de enviados"  # tasa de respuesta
    estados = _barras([("Leído", n["leidos"]), ("Entregado, sin leer", n["entregados"] - n["leidos"]),
                       ("Enviado, sin confirmar entrega", n["sin_confirmar"]), ("Fallido", n["fallidos"]),
                       ("Rechazado", n["rechazados"]),
                       ("Pendiente", total - n["entregados"] - n["sin_confirmar"] - n["fallidos"] - n["rechazados"])],
                      total=total)
    estados = [e for e in estados if e["n"] != "0"]

    # Respuestas: se interpretan con los significados de la campaña (si es de una empresa de la base).
    columnas = ["empresa", "difusion", "telefono", "leido_en", "despachado_en", "respuesta"]
    a = R.analizar(df[respondio][columnas], significados or {}) if respuestas_cliente else         pd.DataFrame(columns=[*columnas, "tipo", "sentido", "motivos", "calificacion"])
    respuestas = {"total": _n(len(a))}
    if not a.empty:
        respuestas["tipos"] = _barras(a["tipo"].value_counts().items())
        respuestas["sentido"] = _barras([(s, int((a["sentido"] == s).sum())) for s in R.SENTIDOS
                                         if (a["sentido"] == s).any()])
        motivos = a["motivos"].explode().dropna()
        if not motivos.empty:
            conteo = motivos.value_counts()
            respuestas["motivos"] = _barras(conteo.head(15).items(), total=len(a))
            respuestas["mas_motivos"] = max(len(conteo) - 15, 0)
        notas = a["calificacion"].dropna()
        if not notas.empty:
            respuestas["notas"] = _barras([(f"{int(k)} ★", int((notas == k).sum())) for k in range(5, 0, -1)],
                                          total=len(notas))
            respuestas["promedio"] = f"{notas.astype(float).mean():.1f}".replace(".", ",")

    # Detalle por línea (compacto: índices en vez de textos repetidos).
    envios = sorted(df["campana"].unique(), key=lambda c: (analisis._es_prueba(c), c))
    i_envio = {c: i for i, c in enumerate(envios)}
    tipos = list(a["tipo"].unique()) if not a.empty else []
    tipo_de = dict(zip(a.index, a["tipo"])) if not a.empty else {}
    sentido_de = dict(zip(a.index, a["sentido"])) if not a.empty else {}
    recep = pd.Series(3, index=df.index)
    recep[entregado] = 0
    recep[fallido] = 1
    recep[rechazado] = 2
    filas = []
    for idx, tel, envio, rc, le, resp, si in zip(df.index, df["telefono"], df["campana"], recep, leido,
                                                   df["respuesta"].fillna(""), respondio):
        t = tipo_de.get(idx)
        texto = " ".join(str(resp).split())[:MAX_TEXTO] if respuestas_cliente else ""
        filas.append([str(tel or ""), i_envio[envio], int(rc), 0 if le else 1,
                      tipos.index(t) if t is not None else -1, sentido_de.get(idx, ""), texto, 1 if si else 0])
    detalle = {"envios": [_parte(e) for e in envios], "recepcion": RECEPCION, "lectura": LECTURA, "tipos": tipos,
               "filas": filas, "con_respuestas": respuestas_cliente}

    # Indicadores comunes con el Dashboard. Sin precios: el reporte de la empresa no lleva costos.
    ind = indicadores.calcular(df, a if respuestas_cliente else None)
    cal = ind["calidad"]
    mayor_cal = max([f["n"] for f in cal["filas"]] or [1]) or 1
    sat = ind["satisfaccion"] if respuestas_cliente else None
    rep = indicadores.repetidos(df)
    detalle["repetidos"] = [[str(r["Número"]), int(r["Veces"]), r["Envíos"],
                             pd.Timestamp(r["Primer envío"]).strftime("%d/%m/%Y %H:%M"),
                             pd.Timestamp(r["Último envío"]).strftime("%d/%m/%Y %H:%M"), r["Se entregó"], r["Respondió"]]
                            for _, r in rep.iterrows()]

    fechas = df["despachado_en"].dropna()
    return {
        "ind_tarjetas": indicadores.tarjetas(ind, ".", ","),
        "horario": _vista_horario(ind["horario"]),
        "mapa": _vista_mapa(ind["mapa"]),
        "calidad": {"filas": [{**f, "n_txt": _n(f["n"]), "pct_txt": _pct(f["n"], total),
                               "ancho": f"{100 * f['n'] / mayor_cal:.1f}"} for f in cal["filas"]],
                    "numeros_repetidos": _n(cal["numeros_repetidos"]), "hay_repetidos": cal["numeros_repetidos"] > 0,
                    "pct_problemas": indicadores.pct(cal["pct_problemas"], ","),
                    "contactos_validos": _n(cal["contactos_validos"])},
        "satisfaccion": {
            "csat": indicadores.pct(sat["csat"], ",") if "csat" in sat else None,
            "promedio": f"{sat['promedio']:.1f}".replace(".", ",") if "promedio" in sat else None,
            "calificaron": _n(sat["calificaron"]) if "calificaron" in sat else None,
            "neto": f"{sat['sentimiento_neto'] * 100:+.1f} pts".replace(".", ",") if "sentimiento_neto" in sat else None,
            "positivas": _n(sat.get("positivas", 0)), "negativas": _n(sat.get("negativas", 0)),
        } if sat else None,

        "campana": df["difusion"].iloc[0], "empresa": df["empresa"].iloc[0], "plataforma": df["plataforma"].iloc[0],
        "categoria": ", ".join(sorted({str(c) for c in df["categoria"].dropna() if str(c) not in ("", "—")})) or "—",
        "desde": fechas.min(), "hasta": fechas.max(), "generado": datetime.now(),
        "kpis": kpis, "embudo": embudo, "estados": estados,
        "efectividad": {"efectivas": _n(n["enviados"]), "pct": _pct(n["enviados"], total), "total": _n(total),
                        "no_enviados": _n(total - n["enviados"]),
                        "respondieron": _n(n["respondieron"]), "pct_respuesta": _pct(n["respondieron"], n["enviados"]),
                        "ancho": f"{100 * n['enviados'] / total:.1f}" if total else "0"},
        "rechazo": {"rechazados": _n(n["rechazados"]), "pct": _pct(n["rechazados"], total),
                    "motivos": _motivos(df[rechazado]), "fallidos": _n(n["fallidos"]),
                    "motivos_fallidos": _motivos(df[fallido])},
        "respuestas": respuestas, "con_respuestas": respuestas_cliente,
        "envios_tabla": _tabla_envios(df),
        "detalle": detalle,
    }


def _tabla_envios(df: pd.DataFrame) -> list[dict]:
    filas = []
    for envio, g in sorted(df.groupby("campana"), key=lambda x: (analisis._es_prueba(x[0]), x[1]["despachado_en"].min())):
        total = len(g)
        filas.append({"envio": _parte(envio), "prueba": analisis._es_prueba(envio),
                      "fecha": g["despachado_en"].min(), "total": _n(total),
                      "entregados": _n(g["entregado_en"].notna().sum()),
                      "pct_entrega": _pct(g["entregado_en"].notna().sum(), total),
                      "leidos": _n(g["leido_en"].notna().sum()), "pct_lectura": _pct(g["leido_en"].notna().sum(), total),
                      "respondieron": _n((g["respuesta"] != "").sum())})
    return filas


FUENTES = Path(settings.BASE_DIR) / "nucleo" / "static" / "nucleo" / "fuentes"


@lru_cache(maxsize=None)
def fuentes_css() -> str:
    """Poppins incrustada en el HTML (≈36 KB): el reporte se ve igual sin conexión."""
    reglas = []
    for archivo, peso, estilo in [("poppins-400.woff2", 400, "normal"), ("poppins-500.woff2", 500, "normal"),
                                  ("poppins-600.woff2", 600, "normal"), ("poppins-700.woff2", 700, "normal"),
                                  ("poppins-700-italic.woff2", 700, "italic")]:
        datos = base64.b64encode((FUENTES / archivo).read_bytes()).decode()
        reglas.append(f"@font-face{{font-family:'Poppins';font-style:{estilo};font-weight:{peso};font-display:swap;"
                      f"src:url(data:font/woff2;base64,{datos}) format('woff2')}}")
    return "\n".join(reglas)


@lru_cache(maxsize=None)
def logo(nombre: str) -> str:
    """Logo como data URI: el HTML generado funciona solo, sin conexión ni archivos aparte."""
    return "data:image/png;base64," + base64.b64encode((MARCA / nombre).read_bytes()).decode()
