"""Piezas de pantalla compartidas por Dashboard e Informe.

Los gráficos se muestran siempre para UNA campaña elegida: cada campaña tiene su propia encuesta,
así que mezclar campañas en un mismo gráfico confunde."""
import pandas as pd
import streamlit as st

import datos
import graficos
import reports
import respuestas as R


def tarjeta(nombre: str, fabricar, clave: str, alto: int, donde=st, vacio: str | None = None, **opciones):
    """Tarjeta con título fijo y un skeleton del alto del gráfico mientras se calcula.

    Devuelve el evento de selección de st.plotly_chart (o None)."""
    with donde.container(border=True):
        st.markdown(f"**{graficos.TITULOS[nombre]}**")
        lugar = st.container()
        with lugar.skeleton(height=alto):
            g = fabricar()
            if g is None:
                lugar.info(vacio or "Sin datos para mostrar.")
                return None
            # El subtítulo va fuera del gráfico: así hace salto de línea en pantallas angostas.
            subtitulo = (g.fig.layout.meta or {}).get("subtitulo")
            if subtitulo:
                lugar.caption(subtitulo)
            evento = lugar.plotly_chart(g.fig, width="stretch", key=clave, alt=g.titulo,
                                        config={"displaylogo": False, "responsive": True}, **opciones)
            lugar.caption(g.explicacion)
            return evento


# Ancho mínimo de cada tarjeta de gráfico: debajo de esto pasan a una sola columna.
ANCHO_TARJETA = 460


def fila_tarjetas():
    """Grilla de 2 tarjetas que pasa a 1 columna cuando no caben (tablet vertical, celular)."""
    return st.grid(2, min_column_width=ANCHO_TARJETA, gap="medium")


def metricas(items, donde=st):
    """Indicadores en una grilla de hasta 4 columnas (sin cortar los números): 4 + 3 en escritorio,
    2 por fila en celular.

    items: [(etiqueta, valor, delta o None)]."""
    with donde.grid(4, min_column_width=150, gap="small"):
        for etiqueta, valor, delta in items:
            # Sin flecha: el % es la parte del total, no una subida.
            st.metric(etiqueta, valor, delta, delta_color="off", delta_arrow="off", border=True, height="stretch")


def kpis(df, donde=st):
    metricas([(n, f"{v:,}", f"{p:.1%}" if p is not None else None) for n, (v, p) in reports.kpis(df).items()], donde)


def alto_tabla(filas: int, maximo: int = 12) -> int:
    """Alto de un st.dataframe: 35 px por fila + encabezado + barra horizontal; desde `maximo` filas, scroll."""
    return 35 * (min(max(filas, 1), maximo) + 1) + 24


def _puntos(evento) -> list:
    if evento is None:
        return []
    return evento.selection.points if hasattr(evento, "selection") else evento["selection"]["points"]


def _elegidos(evento, eje: str) -> list:
    return sorted({p[eje] for p in _puntos(evento) if eje in p})


def _ir_a_significados(empresa: str, campana: str):
    st.session_state["sig_destino"] = (empresa, campana)
    st.switch_page("app_pages/campanas.py")


def campana(df_c: pd.DataFrame, clave: str):
    """Vista completa de UNA campaña: datos generales, envío (lote y pruebas), errores y su encuesta."""
    empresa, nombre = df_c["empresa"].iloc[0], df_c["difusion"].iloc[0]
    info = reports.informe_campanas(df_c).iloc[0]

    # Encabezado: el botón baja debajo del título cuando no hay espacio al lado.
    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        c1 = st.container(width="stretch")
        c2 = st.container(width="content")
        c1.markdown(f"### {nombre}")
        c1.caption(f"**Empresa:** {empresa} · **Categoría:** {info['categoria']} · "
                   f"**Solicitado por:** {info['solicitado_por'] or '—'} · "
                   f"**Fecha de solicitud:** {info['fecha_solicitud'] if pd.notna(info['fecha_solicitud']) else '—'} · "
                   f"**Primer envío:** {pd.Timestamp(info['primer_envio']):%Y-%m-%d %H:%M} · "
                   f"**Lote:** {int(info['mensajes_lote']):,} mensajes · "
                   f"**Pruebas:** {int(info['pruebas'])} ({int(info['mensajes_prueba']):,} mensajes)")
        if c2.button("Configurar significados", key=f"{clave}_ir_sig", icon=":material/tune:",
                     help="Define qué significa cada respuesta de esta campaña y si es positiva o negativa."):
            _ir_a_significados(empresa, nombre)

    kpis(df_c)

    a1 = a2 = fila_tarjetas()
    tarjeta("embudo", lambda: graficos.embudo(df_c), f"{clave}_embudo", graficos.alto("embudo"), donde=a1)
    tarjeta("resultado_envio", lambda: graficos.resultado_por_envio(df_c), f"{clave}_envio",
            graficos.alto("resultado_envio", df_c), donde=a2)
    tarjeta("errores", lambda: graficos.errores(df_c), f"{clave}_errores", graficos.alto("errores", df_c),
            vacio="Esta campaña no tuvo errores.")

    st.markdown("**Detalle por lote y prueba**")
    detalle = reports.por_campana(df_c)
    st.dataframe(reports.presentar(detalle), hide_index=True, width="stretch",
                 height=alto_tabla(len(detalle), 10), alt="Detalle por lote y prueba")

    panel_respuestas(df_c, clave)


@st.fragment
def panel_respuestas(df_c: pd.DataFrame, clave: str):
    """Encuesta de UNA campaña; un clic (o Shift+clic) en las barras filtra la tabla de abajo.

    Es un fragmento: al hacer clic solo se recarga este panel, no toda la página."""
    st.subheader("Respuestas de clientes")
    if not (df_c["respuesta"].fillna("") != "").any():
        st.info("Ningún cliente respondió en esta campaña.")
        return
    a = datos.respuestas(df_c)
    opciones = dict(on_select="rerun", selection_mode="points")

    c1 = c2 = fila_tarjetas()
    ev_sentido = tarjeta("sentido", lambda: graficos.sentido(a), f"{clave}_sentido",
                         graficos.alto("sentido", a=a), donde=c1, **opciones)
    ev_tipo = tarjeta("tipos_respuesta", lambda: graficos.tipos_respuesta(a), f"{clave}_tipos",
                      graficos.alto("tipos_respuesta", a=a), donde=c2, **opciones)
    ev_nota = None
    if a["calificacion"].notna().any():
        ev_nota = tarjeta("calificaciones", lambda: graficos.calificaciones(a), f"{clave}_notas",
                          graficos.alto("calificaciones"), **opciones)
    ev_motivo = tarjeta("motivos", lambda: graficos.motivos(a), f"{clave}_motivos", graficos.alto("motivos", a=a),
                        vacio="Las respuestas de esta campaña no traen opciones ni motivos.", **opciones)

    sentidos, tipos = _elegidos(ev_sentido, "y"), _elegidos(ev_tipo, "y")
    notas, motivos = _elegidos(ev_nota, "x"), _elegidos(ev_motivo, "y")

    st.markdown("**Clientes que respondieron así**")
    if not (sentidos or tipos or notas or motivos):
        st.info("Haz clic en una barra de los gráficos de arriba para ver qué clientes respondieron así. "
                "Con Shift + clic eliges varias barras; haz doble clic en un espacio vacío del gráfico para quitar la selección.",
                icon=":material/touch_app:")
        return

    m = pd.Series(True, index=a.index)
    partes = []
    if sentidos:
        m &= a["sentido"].isin(sentidos)
        partes.append("sentido: " + ", ".join(sentidos))
    if tipos:
        m &= a["tipo"].isin(tipos)
        partes.append("tipo: " + ", ".join(tipos))
    if notas:
        m &= a["calificacion"].isin([int(n) for n in notas])
        partes.append("calificación: " + ", ".join(map(str, notas)))
    if motivos:
        m &= a["motivos"].map(lambda ms: any(x in ms for x in motivos))
        partes.append("respuesta: " + ", ".join(motivos))
    elegidos = a[m]
    st.caption(f"{len(elegidos):,} cliente(s) · " + " · ".join(partes) + ". Las selecciones de distintos gráficos se combinan.")

    lugar = st.container()
    with lugar.skeleton(height=alto_tabla(len(elegidos), 15)):
        lista = R.lista_legible(elegidos)
        lugar.dataframe(lista, hide_index=True, width="stretch", height=alto_tabla(len(lista), 15),
                        alt="Clientes que respondieron así",
                        column_config={"Calificación": st.column_config.NumberColumn(format="%d ★"),
                                       "Fecha": st.column_config.DatetimeColumn(format="YYYY-MM-DD HH:mm")})
        lugar.download_button("Descargar esta lista (CSV)", lista.to_csv(index=False).encode("utf-8-sig"),
                              f"respondieron_{clave}.csv", mime="text/csv", icon=":material/download:")


def tablas_por_campana(df: pd.DataFrame, elegidas: list):
    """Informe de VARIAS campañas en pantalla: sin gráficos, una tabla de respuestas (y de errores) por campaña."""
    for b in reports.por_campana_informe(df, elegidas):
        with st.container(border=True):
            st.markdown(f"**{b['campana']}**")
            st.caption(f"{b['empresa']} · {b['mensajes']:,} mensajes · {b['respondieron']:,} respondieron")
            if "respuestas" in b:
                if b["respuestas"].empty:
                    st.info("Sin respuestas de clientes.")
                else:
                    st.dataframe(b["respuestas"], hide_index=True, width="stretch",
                                 height=alto_tabla(len(b["respuestas"]), 12), alt=f"Respuestas · {b['campana']}")
            if "errores" in b and not b["errores"].empty:
                st.markdown("Errores")
                st.dataframe(b["errores"], hide_index=True, width="stretch",
                             height=alto_tabla(len(b["errores"]), 6), alt=f"Errores · {b['campana']}")
