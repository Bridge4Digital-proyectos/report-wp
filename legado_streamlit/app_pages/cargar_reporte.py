from datetime import date

import streamlit as st

import db
import reports
import vista
from importers import PLATAFORMAS

st.title("Cargar reporte")

con = db.conectar()
NUEVA = "➕ Nueva empresa"

c1, c2 = st.columns(2)
plataforma = c1.selectbox("Plataforma", list(PLATAFORMAS))
empresas = dict((nombre, i) for i, nombre in db.empresas(con))
eleccion = c2.selectbox("Empresa", [*empresas, NUEVA])
if eleccion == NUEVA:
    nombre_nueva = c2.text_input("Nombre de la nueva empresa").strip()

importador = PLATAFORMAS[plataforma]
if not importador.LISTO:
    st.warning(f"El importador de {plataforma} aún no está listo. Comparte un reporte de ejemplo para implementarlo.")
    st.stop()

AYUDA = {
    "Connectly": "Sube el CSV de difusiones exportado desde Connectly.",
    "S1": "Sube el Excel **Detalle de Difusiones** exportado desde S1 (sirve para cualquier empresa). "
          "S1 no trae el texto de las respuestas: los mensajes con **Caso ID** cuentan como «Abrió un caso».",
}
st.caption(AYUDA.get(plataforma, ""))
archivo = st.file_uploader("Archivo del reporte (CSV o Excel)", type=["csv", "xlsx", "xls"])
if not archivo:
    st.stop()

try:
    df = importador.parse(archivo)
except ValueError as e:
    st.error(str(e))
    st.stop()

# Campañas del archivo: se pueden quitar o renombrar antes de comparar y guardar.
st.subheader("Campañas del archivo")
st.caption("Desmarca las campañas que no quieras cargar. Si cambias el nombre de una campaña, se cambia en "
           "todos sus envíos (lote y pruebas), que conservan su final: «. Lote 001», «. Prueba 003»…")
grupos = reports.agrupar_campanas(df["campana"].unique())
df = df.assign(_campana=df["campana"].map(grupos))
lista = (df.groupby("_campana", sort=False)
         .agg(envios=("campana", "nunique"), mensajes=("campana", "size")).reset_index()
         .rename(columns={"_campana": "original"}))
lista.insert(0, "incluir", True)
lista.insert(1, "nombre", lista["original"])
editado = st.data_editor(
    lista, hide_index=True, width="stretch", key=f"campanas_{archivo.name}_{archivo.size}",
    disabled=["original", "envios", "mensajes"], alt="Campañas del archivo",
    column_config={
        "incluir": st.column_config.CheckboxColumn("Cargar"),
        "nombre": st.column_config.TextColumn("Campaña", required=True),
        "original": None,
        "envios": st.column_config.NumberColumn("Lotes y pruebas"),
        "mensajes": st.column_config.NumberColumn("Mensajes"),
    },
)
nombres = {f.original: (f.nombre or "").strip() or f.original for f in editado.itertuples() if f.incluir}
if not nombres:
    st.warning("Marca al menos una campaña para cargar.")
    st.stop()
df = df[df["_campana"].isin(nombres)].copy()
renombrar = df["_campana"].map(nombres) != df["_campana"]
df.loc[renombrar, "campana"] = [reports.renombrar_envio(e, nombres[c])
                                for e, c in zip(df.loc[renombrar, "campana"], df.loc[renombrar, "_campana"])]
df["_campana"] = df["_campana"].map(nombres)

empresa_id = empresas.get(eleccion)

# Comparación con lo ya guardado, antes de guardar nada (solo lectura).
comp = db.comparar_carga(con, df, plataforma, empresa_id) if empresa_id else None
if comp is not None and not comp.empty and comp["sin_cambios"].sum() + comp["actualizadas"].sum() > 0:
    nuevas, actualizadas = int(comp["nuevas"].sum()), int(comp["actualizadas"].sum())
    if nuevas == 0 and actualizadas == 0:
        anterior = db.ultima_carga(con, archivo.name, empresa_id)
        st.info(f"Los {len(df):,} mensajes de este archivo ya estaban guardados para {eleccion} y no traen "
                "ningún cambio, así que no hace falta cargarlo."
                + (f" Este archivo se cargó por última vez el {anterior.replace('T', ' a las ')}." if anterior else ""),
                title="Este reporte ya estaba cargado")
        st.stop()
    st.warning("Parte de este reporte ya estaba guardado. Al guardar se agregan los mensajes nuevos y se "
               "actualizan los que cambiaron (más lecturas, respuestas, etc.). Nada de lo guardado se borra.",
               title="Este reporte actualiza uno ya cargado")
    tabla = comp.assign(fallidos=comp["fallidos_antes"].astype(str) + " → " + comp["fallidos_despues"].astype(str))
    tabla = tabla[["campana", "mensajes", "nuevas", "actualizadas", "sin_cambios",
                   "entregados", "leidos", "respuestas", "opt_outs", "fallidos"]]
    numero = st.column_config.NumberColumn
    st.dataframe(tabla, hide_index=True, width="stretch", alt="Cambios frente a lo ya guardado", column_config={
        "campana": st.column_config.TextColumn("Campaña"),
        "mensajes": numero("Mensajes en archivo"),
        "nuevas": numero("Nuevos"),
        "actualizadas": numero("Con cambios"),
        "sin_cambios": numero("Sin cambios"),
        "entregados": numero("Entregados", format="%+d"),
        "leidos": numero("Leídos", format="%+d"),
        "respuestas": numero("Respuestas", format="%+d"),
        "opt_outs": numero("Opt-outs", format="%+d"),
        "fallidos": st.column_config.TextColumn("Fallidos (antes → después)"),
    })

st.subheader("Vista previa")
vista.metricas([("Mensajes", f"{len(df):,}", None)]
               + [(e, f"{int((df['estado'] == e).sum()):,}", None) for e in ["Leído", "Entregado", "Enviado", "Fallido"]])

st.subheader("Datos de cada campaña")
st.caption("Se aplican a todos los envíos de la campaña (lote y pruebas). La categoría viene marcada como "
           "UTILITY salvo que la campaña ya exista o el archivo diga otra cosa.")

solicitantes = db.solicitantes(con)
datos = {}
with st.form("campanas"):
    for campana, grupo in df.groupby("_campana", sort=False):
        envios = list(grupo["campana"].unique())
        previas = [b for e in envios if empresa_id and (b := db.buscar_campana(con, plataforma, e, empresa_id))]
        previa = previas[0] if previas else {}
        cat_archivo = grupo["categoria_plantilla"].dropna()
        categoria = previa.get("categoria") or (cat_archivo.iloc[0] if not cat_archivo.empty else "UTILITY")
        st.markdown(f"**{campana}** · {len(envios)} envío(s) · {len(grupo):,} mensajes"
                    + (" · *ya existía*" if previa else ""))
        a = b = c = st.grid(3, min_column_width=220)
        cat = a.selectbox("Categoría Meta", db.CATEGORIAS,
                          index=0 if categoria.upper() != "MARKETING" else 1, key=f"cat_{campana}")
        anterior = previa.get("solicitado_por")
        opciones = sorted({*solicitantes, *([anterior] if anterior else [])})
        quien = b.selectbox("Solicitado por", opciones,
                            index=opciones.index(anterior) if anterior else None,
                            accept_new_options=True, placeholder="Escribe o elige un nombre",
                            key=f"quien_{campana}")
        fecha_previa = previa.get("fecha_solicitud")
        cuando = c.date_input("Fecha de solicitud", key=f"fecha_{campana}",
                              value=date.fromisoformat(fecha_previa) if fecha_previa else None)
        for e in envios:
            datos[e] = {"categoria": cat, "solicitado_por": quien,
                        "fecha_solicitud": cuando.isoformat() if cuando else None}
    hay_previos = comp is not None and not comp.empty and comp["nuevas"].sum() < len(df)
    guardar = st.form_submit_button("Guardar actualización" if hay_previos else "Guardar reporte", type="primary")

if guardar:
    if eleccion == NUEVA:
        if not nombre_nueva:
            st.error("Escribe el nombre de la nueva empresa.")
            st.stop()
        empresa_id = db.crear_empresa(con, nombre_nueva)
    antes = db.comparar_carga(con, df, plataforma, empresa_id)
    nuevas, actualizadas, sin_cambios = db.guardar_carga(con, df, plataforma, empresa_id, archivo.name, datos)
    st.cache_data.clear()  # el Dashboard y el Informe vuelven a leer la base
    partes = [f"{nuevas:,} mensajes nuevos"]
    if actualizadas:
        mejoras = [f"{int(antes[c].sum()):+,} {txt}" for c, txt in
                   [("respuestas", "respuestas"), ("leidos", "leídos"), ("entregados", "entregados")]
                   if antes[c].sum()]
        partes.append(f"{actualizadas:,} actualizados" + (f" ({', '.join(mejoras)})" if mejoras else ""))
    if sin_cambios:
        partes.append(f"{sin_cambios:,} sin cambios")
    st.success("Guardado: " + ", ".join(partes) + ".")
