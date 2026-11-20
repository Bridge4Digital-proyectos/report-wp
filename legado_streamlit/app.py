"""Entrada de la app. Ejecutar con: streamlit run app.py"""
import streamlit as st

st.set_page_config(page_title="Reportes de difusiones", page_icon="📊", layout="wide")

pagina = st.navigation([
    st.Page("app_pages/dashboard.py", title="Dashboard", icon=":material/dashboard:", default=True,
            help="KPIs, gráficos y resumen por campaña, con filtros por empresa, fechas y categoría."),
    st.Page("app_pages/cargar_reporte.py", title="Cargar reporte", icon=":material/upload_file:",
            help="Sube un CSV de Connectly; detecta si ya estaba cargado y qué cambió antes de guardar."),
    st.Page("app_pages/campanas.py", title="Campañas", icon=":material/campaign:",
            help="Corrige la categoría Meta, quién solicitó y la fecha de solicitud de cada envío."),
    st.Page("app_pages/empresas.py", title="Empresas", icon=":material/apartment:",
            help="Crea empresas y corrige sus nombres."),
    st.Page("app_pages/informe.py", title="Informe", icon=":material/description:",
            help="Informe filtrado en pantalla y descarga en Excel o PDF."),
    st.Page("app_pages/historial.py", title="Historial de cargas", icon=":material/history:",
            help="Totales guardados y los últimos reportes subidos."),
])
pagina.run()
