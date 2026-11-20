import streamlit as st

import db
import reports
import vista

st.title("Historial de cargas")
st.caption("Totales guardados y los últimos reportes que subiste.")

if "_borrado_ok" in st.session_state:
    st.success(f"Datos borrados. Respaldo guardado en: {st.session_state.pop('_borrado_ok')}")

con = db.conectar()
with st.skeleton(height=vista.alto_tabla(12)):
    campanas = db.campanas(con)
    cargas = db.historial_cargas(con)

meses = st.multiselect("Mes", reports.meses_ordenados(campanas["primer_envio"]), placeholder="Todos",
                       help="Los totales se filtran por el mes del primer envío; las cargas, por el mes en que se subieron.")
if meses:
    campanas = campanas[reports.etiqueta_mes(campanas["primer_envio"]).isin(meses).values]
    cargas = cargas[reports.etiqueta_mes(cargas["Fecha de carga"]).isin(meses).values]

vista.metricas([("Empresas", f"{campanas['empresa'].nunique():,}", None),
                ("Envíos (lotes y pruebas)", f"{len(campanas):,}", None),
                ("Mensajes", f"{int(campanas['mensajes'].sum()) if not campanas.empty else 0:,}", None)])

st.subheader("Últimas cargas")
if cargas.empty:
    st.info("No hay cargas para mostrar.")
else:
    st.dataframe(cargas, hide_index=True, width="stretch", height=vista.alto_tabla(len(cargas), 15), alt="Últimas cargas")

st.divider()
with st.expander("Zona de peligro: borrar todos los datos", icon=":material/warning:"):
    st.warning("Esto borra **todas** las empresas, campañas, mensajes y el historial de cargas: "
               "la aplicación queda como nueva. Antes se guarda automáticamente una copia de respaldo "
               "en la carpeta `data/respaldos`.")
    confirmacion = st.text_input("Para confirmar, escribe BORRAR", key="confirmar_borrado")
    if st.button("Borrar todos los datos", type="primary", icon=":material/delete_forever:",
                 disabled=confirmacion.strip() != "BORRAR"):
        respaldo = db.borrar_todo(con)
        st.cache_data.clear()
        for clave in list(st.session_state.keys()):
            del st.session_state[clave]
        st.session_state["_borrado_ok"] = str(respaldo)
        st.rerun()
