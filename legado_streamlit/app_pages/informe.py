from datetime import datetime

import streamlit as st

import datos
import filtros
import reports
import vista

st.title("Informe")

with st.skeleton(height=120):
    todo = datos.mensajes()
if todo.empty:
    st.info("Todavía no hay reportes cargados.")
    st.stop()

df, elegido = filtros.aplicar(todo, "inf")
if df.empty:
    st.warning("Ningún mensaje coincide con los filtros.")
    st.stop()

opciones = reports.campanas_de(df)
mensajes = df.groupby(["empresa", "difusion"]).size()
elegidas = st.multiselect(
    "Campañas del informe", opciones, key="inf_campanas", placeholder="Elige una o más campañas",
    format_func=lambda k: f"{k[1]} · {k[0]} ({mensajes[k]:,} mensajes)",
    help="Con UNA campaña el informe trae sus gráficos y su encuesta. Con varias, una tabla de respuestas "
         "por campaña (cada campaña tiene su propia encuesta, así que no se mezclan en un gráfico).")
secciones = st.multiselect("Secciones del informe", reports.SECCIONES, default=reports.SECCIONES)

if not elegidas:
    st.info("Elige una o más campañas para armar el informe.", icon=":material/ads_click:")
    st.subheader("Campañas disponibles")
    tabla = reports.presentar(reports.informe_campanas(df))
    st.dataframe(tabla, hide_index=True, width="stretch", height=vista.alto_tabla(len(tabla)), alt="Campañas")
    st.stop()
if not secciones:
    st.warning("Elige al menos una sección.")
    st.stop()

claves = df.set_index(["empresa", "difusion"]).index
df = df[claves.isin(elegidas)]
una = len(elegidas) == 1
elegido = {**elegido, "Campañas": "; ".join(c for _, c in elegidas)}


@st.cache_data(show_spinner="Preparando el archivo…", max_entries=4)
def _archivo(tipo: str, datos_, elegidas_: tuple, filtros_txt: tuple, _sig: tuple) -> bytes:
    hacer = reports.excel_bytes if tipo == "excel" else reports.pdf_bytes
    return hacer(datos_, list(elegidas_), dict(filtros_txt))


# Los archivos se generan recién al pulsar el botón (los gráficos tardan unos segundos en exportarse).
marca = datetime.now().strftime("%Y%m%d_%H%M")
args = (df, tuple(secciones), tuple(elegido.items()), datos._congelar(datos.significados()))
b1, b2 = st.columns(2)
b1.download_button("Descargar Excel", lambda: _archivo("excel", *args), f"informe_campanas_{marca}.xlsx",
                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                   type="primary", width="stretch", icon=":material/table:",
                   help=("Hojas: Resumen, Gráficos y Quiénes respondieron." if una else
                         "Hojas: Resumen, Respuestas por campaña y Quiénes respondieron."))
b2.download_button("Descargar PDF", lambda: _archivo("pdf", *args), f"informe_campanas_{marca}.pdf",
                   mime="application/pdf", width="stretch", icon=":material/picture_as_pdf:")

st.caption(" · ".join(f"**{k}:** {v}" for k, v in elegido.items() if k != "Campañas"))

for nombre, tabla in reports.secciones(df, secciones).items():
    st.subheader(nombre)
    st.dataframe(tabla, hide_index=True, width="stretch", height=vista.alto_tabla(len(tabla)), alt=nombre)

if una:
    vista.campana(df, "inf")
elif {"Respuestas de clientes", "Errores"} & set(secciones):
    st.subheader("Respuestas por campaña")
    st.caption("Una tabla por campaña: cada una tiene su propia encuesta. Para ver gráficos, elige una sola campaña.")
    vista.tablas_por_campana(df, secciones)
