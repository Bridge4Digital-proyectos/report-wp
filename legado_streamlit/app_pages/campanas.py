import pandas as pd
import streamlit as st

import datos
import db
import reports
import respuestas as R
import vista

st.title("Campañas")

con = db.conectar()
with st.skeleton(height=vista.alto_tabla(12)):
    camp = db.campanas(con)
if camp.empty:
    st.info("Todavía no hay campañas.")
    st.stop()

# Si se llegó desde el botón "Configurar significados" de una campaña, se abre directo en ella.
destino = st.session_state.pop("sig_destino", None)
if destino:
    st.session_state["sig_campana"] = tuple(destino)
    st.session_state["camp_empresa"] = destino[0]

# Una empresa a la vez: nunca se mezclan campañas de empresas distintas.
camp["mes"] = reports.etiqueta_mes(camp["primer_envio"]).values
f1, f2 = st.columns(2)
empresa_sel = f1.selectbox("Empresa", sorted(camp["empresa"].unique()), key="camp_empresa")
camp = camp[camp["empresa"] == empresa_sel]
empresas = [empresa_sel]
meses = f2.multiselect("Mes", reports.meses_ordenados(camp["primer_envio"]), placeholder="Todos")
t_datos, t_sig = st.tabs(["Datos de campaña", "Significado de respuestas"],
                         default="Significado de respuestas" if destino else None)

with t_datos:
    st.caption("Corrige la categoría Meta, quién solicitó la difusión y cuándo. Edita en la tabla y guarda.")
    vista_camp = camp
    if meses:
        vista_camp = vista_camp[vista_camp["mes"].isin(meses)]
    if empresas:
        vista_camp = vista_camp[vista_camp["empresa"].isin(empresas)]
    vista_camp = vista_camp.drop(columns="mes")
    vista_camp = vista_camp.assign(fecha_solicitud=pd.to_datetime(vista_camp["fecha_solicitud"], errors="coerce").dt.date)

    editado = st.data_editor(
        vista_camp, hide_index=True, width="stretch", key="editor", height=vista.alto_tabla(len(vista_camp), 15),
        disabled=["id", "empresa", "plataforma", "campana", "mensajes", "primer_envio"],
        column_config={
            "id": None,
            "categoria": st.column_config.SelectboxColumn("Categoría Meta", options=db.CATEGORIAS, required=True),
            "solicitado_por": st.column_config.TextColumn("Solicitado por"),
            "fecha_solicitud": st.column_config.DateColumn("Fecha de solicitud", format="YYYY-MM-DD"),
        },
    )

    if st.button("Guardar cambios", type="primary"):
        cols = ["categoria", "solicitado_por", "fecha_solicitud"]
        cambios = 0
        for antes, despues in zip(vista_camp[["id", *cols]].itertuples(index=False),
                                  editado[["id", *cols]].itertuples(index=False)):
            if tuple(antes) != tuple(despues):
                fecha = despues.fecha_solicitud
                db.actualizar_campana(con, int(despues.id), despues.categoria, despues.solicitado_por or None,
                                      fecha.isoformat() if pd.notna(fecha) else None)
                cambios += 1
        if cambios:
            datos.limpiar()  # el Dashboard y el Informe ven los cambios
        st.success(f"{cambios} campaña(s) actualizada(s)." if cambios else "No había cambios.")

with t_sig:
    st.caption("Cada campaña tiene su propio flujo de respuestas. Aquí defines qué significa cada valor que llegó "
               "y si cuenta como respuesta positiva, negativa o neutral. Los gráficos y el informe usan esta configuración.")
    lugar = st.container()
    with lugar.skeleton(height=vista.alto_tabla(10)):
        a = datos.respuestas(datos.mensajes())
    if a.empty:
        st.info("Todavía no hay respuestas de clientes.")
        st.stop()
    a["mes"] = reports.etiqueta_mes(a["fecha"]).values
    filtro = a
    if meses:
        filtro = filtro[filtro["mes"].isin(meses)]
    if empresas:
        filtro = filtro[filtro["empresa"].isin(empresas)]
    conteo = filtro.groupby(["empresa", "difusion"]).size().sort_values(ascending=False)
    if st.session_state.get("sig_campana") not in conteo.index:
        st.session_state.pop("sig_campana", None)
    if conteo.empty:
        st.info("Ninguna campaña con respuestas coincide con los filtros.")
        st.stop()

    elegida = st.selectbox("Campaña", list(conteo.index), key="sig_campana",
                           format_func=lambda k: f"{k[1]} · {k[0]} ({conteo[k]:,} respuestas)")
    empresa, difusion = elegida
    conf = datos.significados().get((empresa, db.normalizar(difusion)), {})
    tabla = R.valores_campana(a, empresa, difusion, conf)

    if conf:
        st.success("Esta campaña ya tiene su configuración guardada.", icon=":material/task_alt:")
    else:
        st.info("Se muestra la sugerencia automática. Revísala, corrige lo necesario y guarda.",
                icon=":material/auto_fix_high:")
    st.markdown("Ejemplo: si en esta campaña **Opción 1** es *Sin señal*, escribe *Sin señal* en Significado y elige "
                "**Negativa**. En las calificaciones solo se usa el Sentido.")

    editado = st.data_editor(
        tabla, hide_index=True, width="stretch", key=f"sig_editor_{empresa}_{difusion}",
        height=vista.alto_tabla(len(tabla), 15), disabled=["Valor", "Clientes"],
        column_config={
            "Valor": st.column_config.TextColumn("Valor que llegó", help="Tal como viene en el reporte."),
            "Clientes": st.column_config.NumberColumn("Clientes", format="%d"),
            "Significado": st.column_config.TextColumn("Significado", help="Cómo quieres verlo en gráficos e informes."),
            "Sentido": st.column_config.SelectboxColumn("Sentido", options=R.SENTIDOS, required=True),
        },
    )
    b1, b2 = st.columns(2)
    if b1.button("Guardar significados", type="primary", width="stretch", icon=":material/save:"):
        db.guardar_significados(con, empresa, difusion,
                                list(editado[["Valor", "Significado", "Sentido"]].itertuples(index=False)))
        datos.limpiar()
        st.success("Guardado. El Dashboard y el Informe ya usan estos significados.")
    if b2.button("Volver a la sugerencia automática", width="stretch", icon=":material/restart_alt:",
                 disabled=not conf):
        db.borrar_significados(con, empresa, difusion)
        datos.limpiar()
        st.rerun()
