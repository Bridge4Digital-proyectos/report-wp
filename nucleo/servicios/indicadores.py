"""Indicadores clave de una difusión (o de todas las de una empresa): los usan el Dashboard y el reporte HTML.

Definiciones:
- Efectividad de gestión = mensajes ENVIADOS / mensajes de la base (indicador principal: la gestión efectiva es
  que el mensaje salió).
- Tasa de respuesta = clientes que respondieron / mensajes enviados.
- Tasa de entrega = entregados / enviados.  Tasa de lectura = leídos / entregados.
- CTR = mensajes con algún clic (botón o enlace) / entregados.
- Calidad de la base: motivos de los mensajes fallidos según el código o el texto del error de WhatsApp/Meta,
  y números repetidos: el mismo número más de una vez DENTRO DE UNA MISMA CAMPAÑA (que un cliente reciba
  campañas distintas es normal y no cuenta como repetido).
- Monto = entregados de cada categoría × precio de la empresa para esa categoría. En el Dashboard (uso
  interno) es el INGRESO de Bridge4 Digital; en lo que recibe la empresa (reporte HTML, Informe) es su COSTO.

Las horas son locales (como vienen en los reportes de Connectly).
"""
from decimal import Decimal

import pandas as pd

from nucleo.servicios import analisis
from nucleo.servicios import respuestas as R

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MAX_DIAS_FECHA = 14  # hasta 14 días el mapa de lectura va por fecha; más, por día de la semana

MOTIVOS_BASE = [
    ("sin_whatsapp", "Número sin WhatsApp o inalcanzable",
     ("131026",), ("undeliverable",)),
    ("bloqueo_meta", "Bloqueado por Meta (experimento o salud del ecosistema)",
     ("131049", "130472"), ("experiment", "healthy ecosystem")),
    ("baja_marketing", "El cliente se dio de baja de mensajes de marketing",
     ("131050",), ("stop receiving marketing",)),
]


# ------------------------------------------------------------------ formato

def num(x, miles: str = ",") -> str:
    return f"{int(round(x)):,}".replace(",", miles) if x is not None and not pd.isna(x) else "—"


def pct(x, decimal: str = ".") -> str:
    return f"{x:.1%}".replace(".", decimal) if x is not None and not pd.isna(x) else "—"


def _div(a, b):
    return a / b if b else None


def duracion(segundos) -> str:
    """1,5 s · 34 min · 2,3 h · 1,4 días."""
    if segundos is None or pd.isna(segundos):
        return "—"
    if segundos < 60:
        return f"{segundos:.1f} s".replace(".", ",").replace(",0 s", " s")
    if segundos < 3600:
        return f"{segundos / 60:.0f} min"
    if segundos < 86400:
        return f"{segundos / 3600:.1f} h".replace(".", ",")
    return f"{segundos / 86400:.1f} días".replace(".", ",")


# ------------------------------------------------------------------ piezas

def _motivo(code, msg) -> str:
    code, msg = str(code or ""), str(msg or "").lower()
    for clave, _, codigos, textos in MOTIVOS_BASE:
        if code in codigos or any(t in msg for t in textos):
            return clave
    return "otro"


def calidad(df: pd.DataFrame) -> dict:
    total = len(df)
    fallidos = df[df["estado"] == "Fallido"]
    motivos = pd.Series([_motivo(c, m) for c, m in zip(fallidos["error_code"], fallidos["error_msg"])],
                        dtype=object) if len(fallidos) else pd.Series(dtype=object)
    filas = []
    for clave, etiqueta, _, _ in MOTIVOS_BASE + [("otro", "Otros errores de envío", (), ())]:
        n = int((motivos == clave).sum())
        filas.append({"clave": clave, "etiqueta": etiqueta, "n": n, "pct": _div(n, total)})
    veces = df.groupby(["difusion", "telefono"]).size()
    repetidos = veces[veces > 1]
    mensajes_repetidos = int(repetidos.sum() - len(repetidos))  # envíos de más al mismo número en la misma campaña
    filas.append({"clave": "repetidos", "etiqueta": "Mensajes de más a números repetidos en la campaña",
                  "n": mensajes_repetidos, "pct": _div(mensajes_repetidos, total)})
    problemas = sum(f["n"] for f in filas)
    return {"filas": filas, "numeros_repetidos": int(len(repetidos)), "problemas": problemas,
            "pct_problemas": _div(problemas, total),
            "contactos_validos": int(df.loc[df["estado"] != "Fallido", "telefono"].nunique())}


def repetidos(df: pd.DataFrame) -> pd.DataFrame:
    """Una fila por número repetido dentro de una misma campaña (para descargar y limpiar la base)."""
    cols = ["Número", "Veces", "Campaña", "Envíos", "Primer envío", "Último envío", "Se entregó", "Respondió"]
    veces = df.groupby(["difusion", "telefono"])["telefono"].transform("size")
    d = df[veces > 1].assign(_respondio=df["respuesta"].fillna("") != "", _entregado=df["entregado_en"].notna())
    if d.empty:
        return pd.DataFrame(columns=cols)
    g = d.groupby(["difusion", "telefono"], sort=False)
    t = g.agg(Veces=("telefono", "size"), Envíos=("campana", lambda s: " | ".join(sorted(set(s)))),
              primero=("despachado_en", "min"), ultimo=("despachado_en", "max"),
              entregado=("_entregado", "any"), respondio=("_respondio", "any")).reset_index()
    t = pd.DataFrame({"Número": t["telefono"], "Veces": t["Veces"], "Campaña": t["difusion"], "Envíos": t["Envíos"],
                      "Primer envío": t["primero"], "Último envío": t["ultimo"],
                      "Se entregó": t["entregado"].map({True: "Sí", False: "No"}),
                      "Respondió": t["respondio"].map({True: "Sí", False: "No"})})
    return t.sort_values(["Veces", "Campaña", "Número"], ascending=[False, True, True]).reset_index(drop=True)


def horario(df: pd.DataFrame) -> dict:
    """Entregas por hora del día (0–23)."""
    horas = df["entregado_en"].dropna().dt.hour
    conteo = horas.value_counts().reindex(range(24), fill_value=0)
    total = int(conteo.sum())
    pico = int(conteo.idxmax()) if total else None
    rapido = (df["entregado_en"] - df["enviado_en"]).dt.total_seconds()
    return {"horas": list(range(24)), "entregas": [int(v) for v in conteo.values], "total": total, "pico": pico,
            "pct_pico": _div(int(conteo.max()), total) if total else None,
            "pct_1min": _div(int((rapido <= 60).sum()), int(rapido.notna().sum()))}


def mapa_lectura(df: pd.DataFrame) -> dict:
    """Lecturas por fecha × hora (o día de la semana × hora si el periodo pasa de 14 días)."""
    leidos = df["leido_en"].dropna()
    if leidos.empty:
        return {"filas": [], "valores": [], "total": 0}
    dias = (leidos.dt.normalize().max() - leidos.dt.normalize().min()).days + 1
    if dias <= MAX_DIAS_FECHA:
        modo = "fecha"
        fechas = pd.date_range(leidos.dt.normalize().min(), leidos.dt.normalize().max(), freq="D")
        clave = leidos.dt.normalize()
        orden = list(fechas)
        etiquetas = [f"{DIAS[f.weekday()]} {f:%d/%m}" for f in fechas]
    else:
        modo = "semana"
        clave = leidos.dt.weekday
        orden = list(range(7))
        etiquetas = DIAS
    tabla = pd.crosstab(clave, leidos.dt.hour).reindex(index=orden, columns=range(24), fill_value=0)
    total = int(tabla.values.sum())
    i, h = divmod(int(tabla.values.argmax()), 24)
    por_hora = tabla.sum(axis=0)
    return {"modo": modo, "filas": etiquetas, "horas": list(range(24)), "valores": tabla.values.tolist(),
            "maximo": int(tabla.values.max()), "total": total,
            "pico": {"fila": etiquetas[i], "hora": h, "n": int(tabla.values[i, h])},
            "hora_pico": int(por_hora.idxmax())}


def tarifas_de(empresa: str) -> dict:
    """{categoría: (precio, moneda)} de la empresa."""
    from nucleo.models import Tarifa

    return {t.categoria: (t.precio, t.moneda) for t in Tarifa.objects.filter(empresa__nombre=empresa)}


SIMBOLO = {"BOB": "Bs"}  # cómo se muestra cada moneda


def _por(total, n):
    return total / n if n else None


def costo(df: pd.DataFrame, tarifas: dict, leidos: int = 0, respondieron: int = 0, clics: int = 0) -> dict:
    """Monto por categoría con los precios de la empresa (ingreso para Bridge4, costo para la empresa),
    y el monto por resultado: por mensaje entregado, leído, cliente que respondió y clic.
    Si falta el precio de alguna categoría, se avisa cuál."""
    entregados = df[df["entregado_en"].notna()].groupby("categoria").size()
    faltan = [c for c in entregados.index if c not in tarifas]
    monedas = {m for _, m in tarifas.values()}
    if not tarifas or faltan:
        return {"disponible": False, "faltan": faltan or list(entregados.index)}
    total = float(sum(Decimal(int(n)) * tarifas[c][0] for c, n in entregados.items()))
    moneda = SIMBOLO.get(m := monedas.pop(), m) if len(monedas) == 1 else "mixta"
    return {"disponible": True, "moneda": moneda, "total": total,
            "por_entregado": _por(total, int(entregados.sum())), "por_leido": _por(total, leidos),
            "por_respuesta": _por(total, respondieron), "por_clic": _por(total, clics),
            "por_categoria": [{"categoria": c, "entregados": int(n), "precio": float(tarifas[c][0]),
                               "costo": float(Decimal(int(n)) * tarifas[c][0])} for c, n in entregados.items()]}


def montos_detalle(df: pd.DataFrame, tarifas: dict) -> dict | None:
    """Montos de TODAS las difusiones del alcance: por campaña, por mes y por categoría (sin ROI).

    None si falta el precio de alguna categoría (el resumen ya avisa cuál)."""
    ent = df[df["entregado_en"].notna()]
    if ent.empty or any(c not in tarifas for c in ent["categoria"].unique()):
        return None
    precio = {c: float(p) for c, (p, _) in tarifas.items()}
    d = df.assign(_entregado=df["entregado_en"].notna(), _leido=df["leido_en"].notna(),
                  _respondio=df["respuesta"].fillna("").str.strip() != "",
                  _clic=(df["clics_boton"].fillna(0) > 0) | (df["clics_link"].fillna(0) > 0),
                  _monto=df["entregado_en"].notna() * df["categoria"].map(precio).fillna(0.0),
                  _mes=df["despachado_en"].dt.to_period("M"))

    def resumen(g):
        t = g.agg(enviados=("enviado_en", "count"), entregados=("_entregado", "sum"), leidos=("_leido", "sum"),
                  respondieron=("_respondio", "sum"), clics=("_clic", "sum"), monto=("_monto", "sum")).reset_index()
        for col, base in [("por_entregado", "entregados"), ("por_leido", "leidos"),
                          ("por_respuesta", "respondieron"), ("por_clic", "clics")]:
            t[col] = t["monto"] / t[base].where(t[base] > 0)
        t["pct"] = t["monto"] / t["monto"].sum() if t["monto"].sum() else 0.0
        return t

    g = d.groupby("difusion")
    por_campana = resumen(g)  # una fila por campaña, aunque mezcle categorías
    por_campana = por_campana.assign(
        categoria=por_campana["difusion"].map(g["categoria"].agg(lambda s: ", ".join(sorted(set(s.dropna()))))),
        inicio=por_campana["difusion"].map(g["despachado_en"].min())).sort_values("monto", ascending=False)
    por_mes = resumen(d.groupby("_mes")).sort_values("_mes")
    por_mes["mes"] = [f"{MESES[p.month - 1]} {p.year}" for p in por_mes["_mes"]]
    por_categoria = resumen(d.groupby("categoria"))
    por_categoria["tarifa"] = por_categoria["categoria"].map(precio)
    total = float(d["_monto"].sum())
    return {"por_campana": por_campana, "por_mes": por_mes, "por_categoria": por_categoria,
            "moneda": SIMBOLO.get(m := next(iter({m for _, m in tarifas.values()})), m), "total": total,
            "campanas": int(por_campana["difusion"].nunique()),
            "por_entregado": _por(total, int(d["_entregado"].sum())),
            "por_respuesta": _por(total, int(d["_respondio"].sum()))}


MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre",
         "Noviembre", "Diciembre"]


def satisfaccion(a: pd.DataFrame | None) -> dict | None:
    """CSAT y sentimiento neto. None si la campaña no tiene calificaciones ni respuestas con sentido."""
    if a is None or a.empty:
        return None
    salida = {}
    notas = a["calificacion"].dropna()
    if not notas.empty:
        notas = notas.astype(float)
        salida.update({"csat": float((notas >= 4).mean()), "promedio": float(notas.mean()), "calificaron": len(notas)})
    pos, neg = int((a["sentido"] == R.POSITIVA).sum()), int((a["sentido"] == R.NEGATIVA).sum())
    if pos or neg:
        salida.update({"sentimiento_neto": (pos - neg) / len(a), "positivas": pos, "negativas": neg,
                       "respuestas": len(a)})
    return salida or None


# ------------------------------------------------------------------ todo junto

def calcular(df: pd.DataFrame, a: pd.DataFrame | None = None, tarifas: dict | None = None) -> dict:
    """Todos los indicadores del alcance (una campaña o la empresa filtrada)."""
    total = len(df)
    enviados = int(df["enviado_en"].notna().sum())
    entregados = int(df["entregado_en"].notna().sum())
    leidos = int(df["leido_en"].notna().sum())
    respondieron = int((df["respuesta"].fillna("").str.strip() != "").sum())
    clic_boton = df["clics_boton"].fillna(0) > 0
    clic_link = df["clics_link"].fillna(0) > 0
    a_entrega = (df["entregado_en"] - df["enviado_en"]).dt.total_seconds()
    a_lectura = (df["leido_en"] - df["entregado_en"]).dt.total_seconds()
    lecturas = a_lectura.dropna()
    mapa = mapa_lectura(df)
    return {
        "total": total, "contactos": int(df["telefono"].nunique()), "enviados": enviados, "entregados": entregados,
        "leidos": leidos, "respondieron": respondieron,
        "efectividad": _div(enviados, total), "tasa_respuesta": _div(respondieron, enviados),
        "tasa_entrega": _div(entregados, enviados),
        "tasa_lectura": _div(leidos, entregados),
        "ctr": _div(int((clic_boton | clic_link).sum()), entregados), "clics": int((clic_boton | clic_link).sum()),
        "ctr_boton": _div(int(clic_boton.sum()), entregados), "ctr_enlace": _div(int(clic_link.sum()), entregados),
        "t_entrega": float(a_entrega.median()) if a_entrega.notna().any() else None,
        "t_lectura": float(lecturas.median()) if not lecturas.empty else None,
        "lectura_1h": _div(int((lecturas <= 3600).sum()), len(lecturas)) if len(lecturas) else None,
        "hora_pico_lectura": mapa.get("hora_pico"),
        "calidad": calidad(df), "horario": horario(df), "mapa": mapa,
        "satisfaccion": satisfaccion(a),
        "costo": (costo(df, tarifas, leidos, respondieron, int((clic_boton | clic_link).sum()))
                  if tarifas is not None else None),
    }


def tarjetas(ind: dict, miles: str = ",", decimal: str = ".") -> list[dict]:
    """Indicadores clave listos para mostrar: [{nombre, valor, nota, destacado}]."""
    p = lambda x: pct(x, decimal)  # noqa: E731
    c = [
        {"nombre": "Efectividad de gestión", "valor": p(ind["efectividad"]), "destacado": True,
         "nota": f"{num(ind['enviados'], miles)} enviados de {num(ind['total'], miles)} mensajes de la base"},
        {"nombre": "Tasa de entrega", "valor": p(ind["tasa_entrega"]),
         "nota": f"{num(ind['entregados'], miles)} entregados de los enviados"},
        {"nombre": "Tasa de lectura", "valor": p(ind["tasa_lectura"]),
         "nota": f"{num(ind['leidos'], miles)} leídos de los entregados"},
        {"nombre": "Tasa de respuesta", "valor": p(ind["tasa_respuesta"]),
         "nota": f"{num(ind['respondieron'], miles)} respondieron de los enviados"},
        {"nombre": "Clics (CTR)", "valor": p(ind["ctr"]),
         "nota": f"{num(ind['clics'], miles)} con clic · botón {p(ind['ctr_boton'])} · enlace {p(ind['ctr_enlace'])}"},
        {"nombre": "Leído en la 1.ª hora", "valor": p(ind["lectura_1h"]), "nota": "de los mensajes leídos"},
        {"nombre": "Tiempo hasta la lectura", "valor": duracion(ind["t_lectura"]),
         "nota": f"mediana · entrega en {duracion(ind['t_entrega'])}"},
    ]
    if ind["hora_pico_lectura"] is not None:
        c.append({"nombre": "Hora con más lecturas", "valor": f"{ind['hora_pico_lectura']:02d}:00",
                  "nota": "mejor momento para enviar"})
    return c
