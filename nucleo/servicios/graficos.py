"""Gráficos Plotly de la app (Dashboard, Informe, PDF y Excel), cada uno con su explicación.

Todos los gráficos salen de aquí para que se vean iguales en pantalla y en los archivos.
"""
from dataclasses import dataclass

import pandas as pd
import plotly.graph_objects as go

from nucleo.servicios import analisis as reports
from nucleo.servicios import indicadores
from nucleo.servicios import respuestas as R

# Colores: los estados son una escala de un solo tono (más oscuro = llegó más lejos) y el fallo,
# el rojo de alerta. Pares de series: azul y naranja.
# Paleta de la marca Bridge4 Digital (validada para daltonismo con etiquetas directas).
AZUL, NARANJA = "#0f45f9", "#eb6834"
COLOR_ESTADO = {"Leído": "#000062", "Entregado": "#0f45f9", "Enviado": "#6192f8",
                "Pendiente": "#c9d8fd", "Fallido": "#d03b3b"}
TINTA, TINTA_SUAVE, REJILLA = "#1d1d1d", "#69727d", "#e6e8ea"
FUENTE = "Poppins, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"


@dataclass
class Grafico:
    titulo: str
    fig: go.Figure
    explicacion: str


def _n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def _p(x) -> str:
    return f"{x:.1%}".replace(".", ",")


def _d(x) -> str:
    return f"{x:.1f}".replace(".", ",")


def _acortar(nombre: str, largo: int = 46) -> str:
    """Nombres largos: conserva el inicio (código) y el final (tema)."""
    if len(nombre) <= largo:
        return nombre
    mitad = (largo - 1) // 2
    return nombre[:mitad].rstrip() + "…" + nombre[-mitad:].lstrip()


def _etiquetas(nombres) -> list[str]:
    vistas, salida = {}, []
    for n in nombres:
        e = _acortar(n)
        vistas[e] = vistas.get(e, 0) + 1
        salida.append(e if vistas[e] == 1 else f"{e} ({vistas[e]})")
    return salida


GRIS = "#9a9893"
COLOR_GRUPO = {R.NEGATIVA: NARANJA, R.POSITIVA: AZUL, R.NEUTRAL: GRIS}
# Calificación 1–5: divergente, naranja (mala) -> gris (3) -> azul (buena).
COLOR_NOTA = {1: "#c4511f", 2: "#f0a27f", 3: "#c9c7c1", 4: "#6192f8", 5: "#0f45f9"}
MAX_MOTIVOS = 20

# Todos los gráficos son de UNA campaña: cada campaña tiene su propia encuesta y su propio flujo.
TITULOS = {
    "categorias": "Difusiones UTILITY y MARKETING",
    "embudo": "Embudo de la campaña",
    "resultado_envio": "Resultado del lote y de cada prueba",
    "errores": "Errores por código",
    "sentido": "Respuestas positivas, neutrales y negativas",
    "calificaciones": "Calificación de los clientes",
    "motivos": "Respuestas elegidas en la encuesta",
    "tipos_respuesta": "Tipo de respuesta",
    "horario_entrega": "Horario de entrega",
    "mapa_lectura": "¿Cuándo leen los clientes?",
}


def n_campanas(df, por_detalle: bool) -> int:
    d = reports.con_difusion(df)
    if por_detalle:
        return d.groupby(["empresa", "plataforma", "difusion", "categoria", "solicitado_por", "fecha_solicitud"],
                         dropna=False).ngroups
    return d["difusion"].nunique()


def alto(nombre: str, df=None, a=None) -> int:
    """Alto en px de cada gráfico; el skeleton de carga usa el mismo valor que la figura."""
    if nombre == "embudo":
        return 320
    if nombre == "horario_entrega":
        return 340
    if nombre == "mapa_lectura":
        filas = len(indicadores.mapa_lectura(df)["filas"]) if df is not None else 7
        return 130 + 26 * max(filas, 3)
    if nombre == "categorias":
        return 340
    if nombre == "resultado_envio":
        return 150 + 34 * max(df["campana"].nunique(), 1)
    if nombre == "errores":
        return 120 + 34 * len(reports.errores(df))
    if nombre == "sentido":
        return 120 + 40 * max(a["sentido"].nunique() if a is not None else 3, 1)
    if nombre == "calificaciones":
        return 340
    if nombre == "motivos":
        n = len({m for ms in a["motivos"] for m in ms}) if a is not None else MAX_MOTIVOS
        return 130 + 30 * min(max(n, 1), MAX_MOTIVOS)
    if nombre == "tipos_respuesta":
        n = a["tipo"].nunique() if a is not None else len(R.TIPOS)
        return 120 + 34 * max(n, 1)
    return 400


def _estilo(fig: go.Figure, subtitulo: str, alto: int, leyenda: bool = True) -> go.Figure:
    # El subtítulo no va dentro de la figura (Plotly no le hace salto de línea y se corta en el celular):
    # la tarjeta lo muestra como texto encima y png() lo vuelve a poner para el PDF y el Excel.
    fig.update_layout(
        meta={"subtitulo": subtitulo},
        height=alto, margin=dict(l=10, r=20, t=20, b=10), font=dict(color=TINTA, size=12, family=FUENTE),
        showlegend=leyenda, legend=dict(orientation="h", yanchor="top", y=-45 / max(alto - 60, 1), x=0, title=None,
                                        traceorder="normal"),
        hoverlabel=dict(bgcolor="white", bordercolor=REJILLA, font=dict(color=TINTA, size=13), align="left"),
        bargap=0.25, separators=", ",
    )
    fig.update_xaxes(gridcolor=REJILLA, zeroline=False)
    fig.update_yaxes(gridcolor=REJILLA, zeroline=False)
    return fig


def embudo(df) -> Grafico:
    k = reports.kpis(df)
    total, env, ent, lei, resp, fal = (k[x][0] for x in
                                       ["Total mensajes", "Enviados", "Entregados", "Leídos", "Respuestas", "Fallidos"])
    etapas = ["Enviados", "Entregados", "Leídos", "Respondieron"]
    valores = [env, ent, lei, resp]
    fig = go.Figure(go.Funnel(
        y=etapas, x=valores, marker=dict(color=AZUL), connector=dict(line=dict(color=REJILLA)),
        # Respondieron: tasa de respuesta sobre los ENVIADOS, no sobre los leídos. Texto corto para el celular.
        texttemplate=["%{value:,}"] + ["%{value:,} · %{percentPrevious:.1%}"] * 2 + ["%{value:,} · %{percentInitial:.1%}"],
        textposition=["inside" if v >= 0.25 * max(valores or [1]) else "outside" for v in valores],
        hovertemplate="<b>%{y}</b>: %{value:,} (%{percentInitial:.1%} de los enviados)<extra></extra>",
    ))
    _estilo(fig, "Cuántos mensajes avanzan en cada paso; el % de respuestas es sobre los enviados", alto("embudo"),
            leyenda=False)
    fig.update_yaxes(gridcolor="rgba(0,0,0,0)")
    texto = (f"De {_n(total)} mensajes, se enviaron {_n(env)}: efectividad de gestión del {_p(env / total)}."
             if total else "")
    if env:
        texto += f" Llegaron al teléfono {_n(ent)} ({_p(ent / env)} de los enviados)"
        texto += f" y se leyeron {_n(lei)} ({_p(lei / ent)} de los entregados)." if ent else "."
    if lei:
        texto += f" Respondieron {_n(resp)} clientes: tasa de respuesta del {_p(resp / env)} sobre los enviados."
    if fal:
        texto += f" {_n(fal)} mensajes fallaron ({_p(fal / total)} del total)."
    return Grafico(TITULOS["embudo"], fig, texto)


def horario_entrega(df) -> Grafico | None:
    """Entregas por hora del día (hora local); la hora pico, en azul marino."""
    h = indicadores.horario(df)
    if not h["total"]:
        return None
    pct = [v / h["total"] for v in h["entregas"]]
    fig = go.Figure(go.Bar(
        x=[f"{x:02d}:00" for x in h["horas"]], y=h["entregas"],
        marker=dict(color=["#000062" if x == h["pico"] else AZUL for x in h["horas"]], cornerradius=4),
        customdata=[_p(v) for v in pct],
        hovertemplate="<b>%{x}</b> · %{y:,} entregas (%{customdata})<extra></extra>",
    ))
    _estilo(fig, "Mensajes entregados en cada hora del día (hora local)", alto("horario_entrega"), leyenda=False)
    fig.update_xaxes(tickangle=0, dtick=2, gridcolor="rgba(0,0,0,0)")
    fig.update_yaxes(title=None)
    texto = (f"La mayor parte se entregó a las {h['pico']:02d}:00 ({_p(h['pct_pico'])} de las entregas)."
             + (f" El {_p(h['pct_1min'])} llegó al teléfono en menos de un minuto desde el envío."
                if h["pct_1min"] is not None else ""))
    return Grafico(TITULOS["horario_entrega"], fig, texto)


DIAS_LARGOS = {"Lun": "lunes", "Mar": "martes", "Mié": "miércoles", "Jue": "jueves", "Vie": "viernes",
               "Sáb": "sábado", "Dom": "domingo"}


def mapa_lectura(df) -> Grafico | None:
    """Mapa de calor de lecturas: fecha (o día de la semana) × hora. Escala de un solo tono, de claro a oscuro."""
    m = indicadores.mapa_lectura(df)
    if not m["total"]:
        return None
    total = m["total"]
    texto_celda = [[f"{_n(v)} lecturas ({_p(v / total)})" for v in fila] for fila in m["valores"]]
    # El color usa la raíz cuadrada: así una hora pico muy alta no deja todo lo demás en blanco.
    # El número real se ve al pasar el mouse.
    fig = go.Figure(go.Heatmap(
        z=[[v ** 0.5 for v in fila] for fila in m["valores"]], x=[f"{h:02d}:00" for h in m["horas"]], y=m["filas"],
        customdata=texto_celda, colorscale=[[0, "#f3f6fd"], [0.2, "#c9d8fd"], [0.55, "#0f45f9"], [1, "#000062"]],
        xgap=2, ygap=2, showscale=False,
        hovertemplate="<b>%{y}</b> · %{x} — %{customdata}<extra></extra>",
    ))
    _estilo(fig, ("Lecturas por día y hora (más oscuro = más lecturas)" if m["modo"] == "fecha"
                  else "Lecturas por día de la semana y hora (más oscuro = más lecturas)"),
            alto("mapa_lectura", df), leyenda=False)
    fig.update_xaxes(dtick=2, gridcolor="rgba(0,0,0,0)", side="bottom")
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    p = m["pico"]
    dia = p["fila"] if m["modo"] == "fecha" else DIAS_LARGOS.get(p["fila"], p["fila"])
    texto = (f"Las lecturas se concentran a las {m['hora_pico']:02d}:00. El momento con más lecturas fue "
             f"{dia} a las {p['hora']:02d}:00 ({_n(p['n'])} lecturas). Enviar cerca de esas horas suele dar más lectura.")
    return Grafico(TITULOS["mapa_lectura"], fig, texto)


COLOR_CATEGORIA = {"UTILITY": AZUL, "MARKETING": NARANJA}


def categorias(df) -> Grafico | None:
    """Dona con cuántas difusiones (campañas completas: lote + pruebas) son UTILITY y cuántas MARKETING."""
    t = reports.por_categoria(df)
    t = t[t["difusiones"] > 0]
    if t.empty:
        return None
    total = int(t["difusiones"].sum())
    fig = go.Figure(go.Pie(
        labels=t["categoria"], values=t["difusiones"], hole=0.62, sort=False, direction="clockwise",
        marker=dict(colors=[COLOR_CATEGORIA.get(c, GRIS) for c in t["categoria"]], line=dict(color="white", width=2)),
        texttemplate="<b>%{label}</b><br>%{value} (%{percent:.1%})", textposition="outside", textfont=dict(color=TINTA, size=13),
        hovertemplate="<b>%{label}</b>: %{value} difusiones (%{percent:.1%})<extra></extra>",
        automargin=True,  # las etiquetas de afuera no se cortan en pantallas angostas
    ))
    _estilo(fig, "Cantidad de difusiones por categoría de Meta", alto("categorias"), leyenda=False)  # cada parte lleva su nombre
    fig.update_layout(margin=dict(l=10, r=10, t=20, b=20),
                      annotations=[dict(text=f"<b>{total}</b><br>difusiones", x=0.5, y=0.5, showarrow=False,
                                        font=dict(size=18, color=TINTA))])
    partes = [f"{_n(f.difusiones)} son {f.categoria} ({_p(f.difusiones / total)})" for f in t.itertuples()]
    texto = f"De {_n(total)} difusiones, " + " y ".join(partes) + ". Cada difusión es una campaña completa (lote y pruebas)."
    return Grafico(TITULOS["categorias"], fig, texto)


def _parte(envio: str) -> str:
    """'Campaña X . Lote 001' -> 'Lote 001' (la parte que distingue al envío dentro de la campaña)."""
    return reports._SEPARADOR.split(str(envio).strip())[-1]


def resultado_por_envio(df) -> Grafico:
    """Barras al 100 % con el estado final de los mensajes del lote y de cada prueba."""
    tabla = df.groupby(["campana", "estado"]).size().unstack(fill_value=0)
    tabla = tabla.reindex(columns=[e for e in COLOR_ESTADO if e in tabla.columns])
    totales = tabla.sum(axis=1)
    # Plotly dibuja de abajo hacia arriba: las pruebas abajo (la 001 más cerca del lote) y el lote arriba.
    pruebas = sorted((e for e in tabla.index if reports._es_prueba(e)), key=_parte, reverse=True)
    lotes = sorted((e for e in tabla.index if not reports._es_prueba(e)), key=_parte, reverse=True)
    orden = pruebas + lotes
    tabla, totales = tabla.loc[orden], totales.loc[orden]
    y = [f"{_parte(e)} ({_n(t)} msj)" for e, t in zip(tabla.index, totales)]
    fig = go.Figure()
    for estado in tabla.columns:
        fig.add_bar(y=y, x=tabla[estado] / totales, name=estado, orientation="h",
                    marker=dict(color=COLOR_ESTADO[estado], line=dict(color="white", width=1)),
                    customdata=tabla[estado],
                    hovertemplate=estado + ": <b>%{customdata:,}</b> (%{x:.1%})<extra></extra>")
    _estilo(fig, "Cómo terminó cada mensaje del lote y de cada prueba (cada barra suma 100 %)",
            alto("resultado_envio", df))
    fig.update_layout(barmode="stack", hovermode="y unified")
    fig.update_xaxes(tickformat=".0%", range=[0, 1], title=None)
    texto = "Azul más oscuro = el mensaje llegó más lejos (leído); rojo = falló."
    lote = [e for e in tabla.index if not reports._es_prueba(e)]
    if lote:
        leidos, total = tabla.loc[lote].get("Leído", pd.Series(0, index=lote)).sum(), totales.loc[lote].sum()
        texto += f" En el lote se leyó el {_p(leidos / total)} de {_n(total)} mensajes."
    pruebas = len(tabla) - len(lote)
    if pruebas:
        texto += f" Hubo {pruebas} prueba(s) con {_n(totales.drop(lote).sum())} mensajes."
    fallidos = tabla.get("Fallido", pd.Series(0, index=tabla.index)).sum()
    texto += f" Fallaron {_n(fallidos)} mensajes en total." if fallidos else " No hubo mensajes fallidos."
    return Grafico(TITULOS["resultado_envio"], fig, texto)


def errores(df) -> Grafico | None:
    e = reports.errores(df)
    if e.empty:
        return None
    e = e.assign(etiqueta=e["error_code"].astype(str).map(lambda c: _acortar(c, 22)) + " · "
                 + e["error_msg"].fillna("").map(lambda m: _acortar(m, 40)))
    e = e.sort_values("cantidad")
    fig = go.Figure(go.Bar(
        y=e["etiqueta"], x=e["cantidad"], orientation="h", marker=dict(color=COLOR_ESTADO["Fallido"]),
        text=e["cantidad"].map(_n), textposition="outside",
        customdata=e["cantidad"] / e["cantidad"].sum(),
        hovertemplate="<b>%{y}</b>: %{x:,} mensajes (%{customdata:.1%})<extra></extra>",
    ))
    _estilo(fig, "Mensajes con cada código de error de WhatsApp", alto("errores", df), leyenda=False)
    fig.update_xaxes(title=None, range=[0, e["cantidad"].max() * 1.15])
    total = e["cantidad"].sum()
    top = e.iloc[-1]
    texto = (f"{_n(total)} mensajes tuvieron algún error. El más frecuente es {top['error_code']} "
             f"({top['error_msg']}), con {_n(top['cantidad'])} casos ({_p(top['cantidad'] / total)}).")
    if str(top["error_code"]) == "131026":
        texto += " Este código suele indicar que el número no tiene WhatsApp o no acepta el mensaje."
    return Grafico(TITULOS["errores"], fig, texto)


def sentido(a) -> Grafico | None:
    """Cuántas respuestas de la campaña fueron positivas, neutrales o negativas (según su configuración)."""
    if a.empty:
        return None
    t = a["sentido"].value_counts().reindex([s for s in R.SENTIDOS[::-1] if s in set(a["sentido"])])
    total = int(t.sum())
    fig = go.Figure(go.Bar(
        y=t.index, x=t.values, orientation="h", marker=dict(color=[COLOR_GRUPO[s] for s in t.index]),
        text=[f"{_n(v)} · {_p(v / total)}" for v in t.values], textposition="outside", customdata=t.values / total,
        hovertemplate="<b>%{y}</b>: %{x:,} clientes (%{customdata:.1%})<extra></extra>",
    ))
    _estilo(fig, "Sentido de cada respuesta según lo definido para esta campaña", alto("sentido", a=a), leyenda=False)
    fig.update_xaxes(title=None, range=[0, t.max() * 1.3])
    texto = (f"De {_n(total)} respuestas, {_n(t.get(R.POSITIVA, 0))} ({_p(t.get(R.POSITIVA, 0) / total)}) fueron "
             f"positivas y {_n(t.get(R.NEGATIVA, 0))} ({_p(t.get(R.NEGATIVA, 0) / total)}) negativas.")
    texto += " Qué cuenta como positiva o negativa se ajusta en Campañas → Significado de respuestas."
    return Grafico(TITULOS["sentido"], fig, texto)


def calificaciones(a) -> Grafico | None:
    """a = respuestas.analizar(df) de una campaña."""
    notas = a["calificacion"].dropna()
    if notas.empty:
        return None
    cuenta = notas.astype(int).value_counts().reindex(range(1, 6), fill_value=0)
    total = int(cuenta.sum())
    fig = go.Figure(go.Bar(
        x=[str(n) for n in cuenta.index], y=cuenta.values, marker=dict(color=[COLOR_NOTA[n] for n in cuenta.index]),
        text=[f"{_n(v)} · {_p(v / total)}" for v in cuenta.values], textposition="outside",
        customdata=cuenta.values / total,
        hovertemplate="<b>Calificación %{x}</b>: %{y:,} clientes (%{customdata:.1%})<extra></extra>",
    ))
    _estilo(fig, "Clientes que dieron cada nota en la encuesta (1 = muy mala, 5 = muy buena)",
            alto("calificaciones"), leyenda=False)
    fig.update_xaxes(title="Calificación", type="category")
    fig.update_yaxes(title="Clientes", range=[0, cuenta.max() * 1.18])
    prom = notas.astype(float).mean()
    alta, baja = cuenta[[4, 5]].sum() / total, cuenta[[1, 2]].sum() / total
    texto = (f"{_n(total)} clientes calificaron el servicio; el promedio es {_d(prom)} de 5. "
             f"El {_p(alta)} dio 4 o 5 y el {_p(baja)} dio 1 o 2.")
    return Grafico(TITULOS["calificaciones"], fig, texto)


def motivos(a) -> Grafico | None:
    filas = [(m, g[m]) for ms, g in zip(a["motivos"], a["grupos"]) for m in ms]
    if not filas:
        return None
    m = pd.DataFrame(filas, columns=["motivo", "grupo"]).value_counts().reset_index(name="n")
    m = m.sort_values("n", ascending=False).groupby("motivo").agg(n=("n", "sum"), grupo=("grupo", "first"))
    m = m.sort_values("n", ascending=False)
    con_motivo = int((a["motivos"].str.len() > 0).sum())
    top = m.head(MAX_MOTIVOS).iloc[::-1]
    fig = go.Figure()
    for grupo in [R.NEGATIVA, R.POSITIVA, R.NEUTRAL]:
        parte = top[top["grupo"] == grupo]
        if parte.empty:
            continue
        fig.add_bar(y=parte.index, x=parte["n"], name=grupo, orientation="h", marker=dict(color=COLOR_GRUPO[grupo]),
                    text=parte["n"].map(_n), textposition="outside", customdata=parte["n"] / con_motivo,
                    hovertemplate="<b>%{y}</b>: %{x:,} clientes (%{customdata:.1%})<extra></extra>")
    extra = f"los {len(top)} más elegidos" if len(m) > len(top) else "todas"
    _estilo(fig, f"Opciones o motivos marcados en la encuesta ({extra}); un cliente puede marcar varios",
            alto("motivos", a=a))
    fig.update_layout(barmode="stack")
    fig.update_yaxes(categoryorder="array", categoryarray=list(top.index))
    fig.update_xaxes(title=None, range=[0, top["n"].max() * 1.15])
    texto = f"{_n(con_motivo)} clientes marcaron al menos una opción."
    for grupo, frase in [(R.NEGATIVA, "La negativa más elegida"), (R.POSITIVA, "La positiva más elegida")]:
        g = m[m["grupo"] == grupo]
        if not g.empty:
            texto += f" {frase} es «{g.index[0]}»: {_n(g['n'].iloc[0])} clientes ({_p(g['n'].iloc[0] / con_motivo)})."
    if m.index.str.startswith("Opción").any():
        texto += (" Las «Opción N» aún no tienen significado: defínelo en Campañas → Significado de respuestas.")
    return Grafico(TITULOS["motivos"], fig, texto)


def tipos_respuesta(a) -> Grafico | None:
    if a.empty:
        return None
    t = a["tipo"].value_counts()
    total = int(t.sum())
    t = t.iloc[::-1]
    fig = go.Figure(go.Bar(
        y=t.index, x=t.values, orientation="h",
        marker=dict(color=[AZUL if i == R.ENCUESTA else "#86b6ef" for i in t.index]),
        text=[f"{_n(v)} · {_p(v / total)}" for v in t.values], textposition="outside", customdata=t.values / total,
        hovertemplate="<b>%{y}</b>: %{x:,} clientes (%{customdata:.1%})<extra></extra>",
    ))
    _estilo(fig, "Qué escribieron los clientes que respondieron (se clasifica automáticamente)",
            alto("tipos_respuesta", a=a), leyenda=False)
    fig.update_xaxes(title=None, range=[0, t.max() * 1.25])
    enc = int(t.get(R.ENCUESTA, 0))
    texto = f"Respondieron {_n(total)} clientes"
    texto += f"; {_n(enc)} ({_p(enc / total)}) completaron la encuesta." if enc else "; ninguno con encuesta."
    resto = t.drop(R.ENCUESTA, errors="ignore").sort_values(ascending=False)
    if not resto.empty:
        texto += f" Entre los demás, lo más frecuente fue «{resto.index[0]}» ({_n(resto.iloc[0])})."
    if "Respuesta automática" in t.index:
        texto += " «Respuesta automática» son contestadores de negocios o bots, no personas."
    return Grafico(TITULOS["tipos_respuesta"], fig, texto)


def significados_guardados() -> dict:
    from nucleo.servicios import datos

    return datos.significados()


def para_campana(df, a=None, secciones=None) -> list[Grafico]:
    """Gráficos de UNA campaña para el informe: envío, errores y su encuesta (sin los que vengan vacíos)."""
    secciones = reports.SECCIONES if secciones is None else secciones
    lista = [embudo(df), resultado_por_envio(df)]
    if "Errores" in secciones:
        lista.append(errores(df))
    if "Respuestas de clientes" in secciones:
        a = R.analizar(reports.con_difusion(df), significados_guardados()) if a is None else a
        lista += [sentido(a), calificaciones(a), motivos(a), tipos_respuesta(a)]
    return [g for g in lista if g]


def png(fig: go.Figure, ancho: int = 1400) -> bytes:
    """Imagen para PDF/Excel, con fondo blanco."""
    f = go.Figure(fig).update_layout(template="plotly_white", paper_bgcolor="white", plot_bgcolor="white")
    subtitulo = (f.layout.meta or {}).get("subtitulo")
    if subtitulo:
        f.update_layout(title=dict(text=f"<span style='font-size:12px;color:{TINTA_SUAVE}'>{subtitulo}</span>",
                                   x=0, xanchor="left"), margin=dict(t=50))
    # Kaleido usa Chrome y a veces falla al arrancar ("kaleido_scopes is not defined"): se reintenta.
    for intento in range(3):
        try:
            return f.to_image(format="png", width=ancho, height=f.layout.height or 400, scale=1)
        except Exception:  # noqa: BLE001 - error interno de Chrome/kaleido, pasajero
            if intento == 2:
                raise
            import time

            time.sleep(0.5 * (intento + 1))
