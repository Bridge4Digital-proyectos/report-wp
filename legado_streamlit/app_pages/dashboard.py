import streamlit as st

import datos
import filtros
import graficos
import reports
import vista

st.title("Dashboard")

with st.skeleton(height=120):
    todo = datos.mensajes()
if todo.empty:
    st.info("Todavía no hay reportes cargados.")
    st.stop()

df, elegido = filtros.aplicar(todo, "dash")
st.caption(f"**{elegido['Empresa']}** · reportes de **{elegido['Plataforma']}**. "
           "Cambia de empresa o plataforma en la barra lateral.")
if df.empty:
    st.warning("Ningún mensaje coincide con los filtros.")
    st.stop()

vista.kpis(df)

# Categorías de Meta: cuenta difusiones completas, no mezcla encuestas.
izq = der = vista.fila_tarjetas()
vista.tarjeta("categorias", lambda: graficos.categorias(df), "dash_categorias", graficos.alto("categorias"), izq)
with der.container(border=True):
    st.markdown("**UTILITY y MARKETING en números**")
    cat = reports.presentar(reports.por_categoria(df))
    st.dataframe(cat, hide_index=True, width="stretch", height=vista.alto_tabla(len(cat)), alt="Por categoría")
    st.caption("UTILITY: mensajes de servicio (avisos, cobranza, encuestas). MARKETING: promociones. "
               "Corrige la categoría de una campaña en **Campañas → Datos de campaña**.")

st.subheader("Resumen por campaña")
st.caption("Cada fila es una campaña completa: suma su lote y sus pruebas. "
           "**Haz clic en una campaña** para ver sus gráficos y su encuesta (cada campaña tiene la suya).")
lugar = st.container()
alto = vista.alto_tabla(graficos.n_campanas(df, True))
with lugar.skeleton(height=alto):
    resumen = reports.por_difusion(df)
    evento = lugar.dataframe(reports.presentar(resumen), hide_index=True, width="stretch", key="resumen_campanas",
                             height=alto, on_select="rerun", selection_mode="single-row", alt="Resumen por campaña")

if not evento.selection.rows:
    st.info("Elige una campaña en la tabla de arriba para ver sus gráficos, su detalle por lote y prueba "
            "y las respuestas de sus clientes.", icon=":material/ads_click:")
    st.stop()

fila = resumen.iloc[evento.selection.rows[0]]
df_c = df[(df["empresa"] == fila["empresa"]) & (df["plataforma"] == fila["plataforma"])
          & (df["difusion"] == fila["difusion"])]
vista.campana(df_c, "dash")
