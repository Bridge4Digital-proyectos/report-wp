import streamlit as st

import datos
import db
import vista

st.title("Empresas")
st.caption("Crea empresas nuevas o corrige su nombre. Los cambios se ven en todas las pantallas e informes.")

con = db.conectar()

if "_empresas_ok" in st.session_state:
    st.success(st.session_state.pop("_empresas_ok"))

with st.form("nueva_empresa", clear_on_submit=True, border=True):
    st.markdown("**Nueva empresa**")
    c1, c2 = st.columns([3, 1], vertical_alignment="bottom")
    nombre = c1.text_input("Nombre", placeholder="Ej.: Tigo Bolivia")
    if c2.form_submit_button("Crear empresa", type="primary", width="stretch", icon=":material/add:"):
        nombre = " ".join(nombre.split())
        existentes = {n.casefold() for _, n in db.empresas(con)}
        if not nombre:
            st.error("Escribe un nombre.")
        elif nombre.casefold() in existentes:
            st.warning(f"Ya existe una empresa llamada «{nombre}».")
        else:
            db.crear_empresa(con, nombre)
            datos.limpiar()
            st.session_state["_empresas_ok"] = f"Empresa «{nombre}» creada."
            st.rerun()

st.subheader("Empresas registradas")
with st.skeleton(height=vista.alto_tabla(8)):
    tabla = db.resumen_empresas(con)
if tabla.empty:
    st.info("Todavía no hay empresas. Crea una arriba o al cargar un reporte.")
    st.stop()

st.caption("Para renombrar, edita el nombre en la tabla y pulsa **Guardar nombres**.")
editado = st.data_editor(
    tabla, hide_index=True, width="stretch", key="editor_empresas", height=vista.alto_tabla(len(tabla), 15),
    disabled=["id", "envios", "mensajes", "ultimo_envio"],
    column_config={
        "id": None,
        "nombre": st.column_config.TextColumn("Empresa", required=True),
        "envios": st.column_config.NumberColumn("Envíos (lotes y pruebas)", format="%d"),
        "mensajes": st.column_config.NumberColumn("Mensajes", format="%d"),
        "ultimo_envio": st.column_config.TextColumn("Último envío"),
    },
)

if st.button("Guardar nombres", type="primary", icon=":material/save:"):
    cambios, errores = 0, []
    for antes, despues in zip(tabla.itertuples(index=False), editado.itertuples(index=False)):
        if (despues.nombre or "").strip() != antes.nombre:
            try:
                db.renombrar_empresa(con, int(despues.id), despues.nombre)
                cambios += 1
            except ValueError as e:
                errores.append(f"«{antes.nombre}»: {e}")
    for e in errores:
        st.error(e)
    if cambios:
        datos.limpiar()
        st.session_state["_empresas_ok"] = f"{cambios} empresa(s) renombrada(s)."
        st.rerun()
    elif not errores:
        st.info("No había cambios.")
