from pathlib import Path

import pandas as pd

import db
import reports
from importers import connectly

CSV = Path(__file__).parent / "fixtures" / "TRABAJO_PROGRAMADO_12_11_26.csv"


def test_parse_connectly():
    crudo = pd.read_csv(CSV, dtype=str)
    df = connectly.parse(CSV)
    assert len(df) == len(crudo)
    assert set(df["campana"]) == {
        "Gestion Gdv 2611 . 014 . Trabajo Programado 12 11 26 . Lote 001",
        "Gestion Gdv 2611 . 014 . TRABAJO PROGRAMADO 12 11 26 . Prueba 001",
    }
    assert (df["respuesta"] != "").sum() == 4
    assert set(df["categoria_plantilla"].dropna()) == {"UTILITY"}
    assert df["estado"].value_counts().sum() == len(df)
    # Con error pero leído: cuenta como Leído y conserva el error.
    fila = df[df["telefono"] == "+59170000014"].iloc[0]
    assert fila["estado"] == "Leído" and fila["error_code"] == "131026"
    # Error sin enviar: Fallido.
    assert df[df["telefono"] == "+59170000026"].iloc[0]["estado"] == "Fallido"
    # Enviado sin entrega ni error.
    assert df[df["telefono"] == "+59170000053"].iloc[0]["estado"] == "Enviado"


def test_guardar_sin_duplicar_y_exportar(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    df = connectly.parse(CSV)
    empresa = db.crear_empresa(con, "Empresa prueba")
    datos = {c: {"categoria": "utility", "solicitado_por": "Ana", "fecha_solicitud": "2026-11-10"}
             for c in df["campana"].unique()}

    assert db.guardar_carga(con, df, "Connectly", empresa, "a.csv", datos) == (len(df), 0, 0)
    # El mismo archivo otra vez: nada nuevo ni cambiado.
    comp = db.comparar_carga(con, df, "Connectly", empresa)
    assert comp["sin_cambios"].sum() == len(df) and comp[["nuevas", "actualizadas"]].sum().sum() == 0
    assert db.guardar_carga(con, df, "Connectly", empresa, "a.csv", datos) == (0, 0, len(df))

    mensajes = db.mensajes(con)
    assert len(mensajes) == len(df)
    k = reports.kpis(mensajes)
    assert k["Total mensajes"][0] == len(df)
    assert k["Respuestas"][0] == 4

    filtros = {"Empresa": "Empresa prueba"}
    assert reports.excel_bytes(mensajes, reports.SECCIONES, filtros)[:2] == b"PK"
    assert reports.pdf_bytes(mensajes, reports.SECCIONES, filtros)[:4] == b"%PDF"


def test_lote_y_prueba_forman_una_campana():
    import reports
    assert reports.difusion("Gdv . Trabajo Programado 12 11 26 . Lote 001") == "Gdv . Trabajo Programado"
    assert reports.difusion("Gdv . TRABAJO PROGRAMADO 12 11 26 . Prueba 001") == "Gdv . TRABAJO PROGRAMADO"
    assert reports.difusion("Gdv . Trabajo Programado 12 11 26 . Reenvio") == "Gdv . Trabajo Programado"
    assert reports.difusion("Campaña sin tramos") == "Campaña sin tramos"


def test_fecha_final_no_separa_la_campana():
    import reports
    a = "Gdv 2611 . 007 . Encuesta Internet Fijo 11 11 26 . Lote 001"
    b = "Gdv 2611 . 007 . ENCUESTA INTERNET FIJO 09 11 26 . Prueba 001"
    assert reports.difusion(a).casefold() == reports.difusion(b).casefold()


def test_reporte_mas_reciente_actualiza_sin_borrar(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    viejo = connectly.parse(CSV)
    empresa = db.crear_empresa(con, "E")
    db.guardar_carga(con, viejo, "Connectly", empresa, "viejo.csv", {})

    # Reporte posterior: 3 respuestas nuevas y 2 lecturas nuevas.
    nuevo = viejo.copy()
    sin_resp = nuevo.index[nuevo["respuesta"] == ""][:3]
    nuevo.loc[sin_resp, "respuesta"] = "Gracias"
    sin_leer = nuevo.index[nuevo["leido_en"].isna() & nuevo["entregado_en"].notna()][:2]
    nuevo.loc[sin_leer, "leido_en"] = "2026-11-12 10:00:00"

    comp = db.comparar_carga(con, nuevo, "Connectly", empresa)
    assert comp["respuestas"].sum() == 3
    assert comp["leidos"].sum() == 2
    assert comp["nuevas"].sum() == 0
    actualizadas = len(set(sin_resp) | set(sin_leer))
    assert comp["actualizadas"].sum() == actualizadas

    assert db.guardar_carga(con, nuevo, "Connectly", empresa, "nuevo.csv", {}) == (0, actualizadas, len(viejo) - actualizadas)
    k = reports.kpis(db.mensajes(con))
    assert k["Respuestas"][0] == 4 + 3

    # Si después se sube el reporte viejo, no se pierde nada.
    db.guardar_carga(con, viejo, "Connectly", empresa, "viejo.csv", {})
    k2 = reports.kpis(db.mensajes(con))
    assert k2["Respuestas"][0] == 7 and k2["Leídos"][0] == k["Leídos"][0]


def test_punto_sin_espacio_antes_del_lote():
    import reports
    n = "Gdv 2611 . 008 . Encuesta Post Cambio De Modem 30 10 26. Lote 002"
    assert reports.difusion(n) == "Gdv 2611 . 008 . Encuesta Post Cambio De Modem"
    assert reports.renombrar_envio(n, "Encuesta Modem") == "Encuesta Modem . Lote 002"


def test_informe_por_campana_con_pruebas(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    db.guardar_carga(con, connectly.parse(CSV), "Connectly", db.crear_empresa(con, "E"), "a.csv", {})
    t = reports.informe_campanas(db.mensajes(con))
    assert len(t) == 1
    fila = t.iloc[0]
    assert (fila["total"], fila["mensajes_lote"], fila["pruebas"], fila["mensajes_prueba"]) == (80, 77, 1, 3)
    assert list(reports.secciones(db.mensajes(con), reports.SECCIONES)) == reports.TABLAS


def test_borrar_todo_deja_la_base_vacia_con_respaldo(tmp_path):
    con = db.conectar(tmp_path / "t.db")
    db.guardar_carga(con, connectly.parse(CSV), "Connectly", db.crear_empresa(con, "E"), "a.csv", {})
    respaldo = db.borrar_todo(con, tmp_path / "respaldos")
    for tabla in ["mensajes", "cargas", "campanas", "empresas"]:
        assert con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0] == 0
    assert db.mensajes(db.conectar(respaldo)).shape[0] == 80


def test_etiqueta_y_orden_de_meses():
    fechas = pd.Series(pd.to_datetime(["2026-11-03", "2026-01-20", None, "2026-11-30"]))
    assert list(reports.etiqueta_mes(fechas)) == ["Noviembre 2026", "Enero 2026", "", "Noviembre 2026"]
    assert reports.meses_ordenados(fechas) == ["Noviembre 2026", "Enero 2026"]


def test_interpretar_formatos_de_respuesta():
    import respuestas as R

    r = R.interpretar('{"aspectos_neutrales":[],"aspectos_positivos":["buena_cobertura"],"problemas":[],"satisfaccion":"4"}')
    assert (r["tipo"], r["calificacion"], r["motivos"]) == (R.ENCUESTA, 4, [("Buena cobertura", R.POSITIVO)])
    r = R.interpretar("calificacion: 2, problemas: otros, problemas_otros: se corta, y es lento")
    assert (r["calificacion"], r["motivos"], r["comentario"]) == (2, [("Otro motivo", R.NEUTRAL)], "se corta, y es lento")
    r = R.interpretar('{"rating":"3","razones":["internet_lento"],"sentimiento":"negativo"}')
    assert (r["calificacion"], r["motivos"]) == (3, [("Internet lento", R.PROBLEMA)])
    r = R.interpretar('{"label_2":["1","5"],"otro_motivo":"Internet inestable "}')
    assert [m for m, _ in r["motivos"]] == ["Opción 1", "Opción 5"] and r["comentario"] == "Internet inestable"
    r = R.interpretar("Buenas noche | aspectos: buena_velocidad, calificacion: 5")
    assert (r["tipo"], r["calificacion"]) == (R.ENCUESTA, 5)
    assert R.interpretar("Hola")["tipo"] == "Saludo"
    assert R.interpretar("Ya pagué")["tipo"] == "Dice que ya pagó"
    assert R.interpretar("This message (type: sticker) is currently unsupported.")["tipo"] == "Sticker, emoji o multimedia"


def test_excel_tiene_tres_hojas(tmp_path):
    from io import BytesIO

    from openpyxl import load_workbook

    con = db.conectar(tmp_path / "t.db")
    db.guardar_carga(con, connectly.parse(CSV), "Connectly", db.crear_empresa(con, "E"), "a.csv", {})
    libro = load_workbook(BytesIO(reports.excel_bytes(db.mensajes(con), reports.SECCIONES, {"Filtros": "Ninguno"})))
    assert libro.sheetnames == ["Resumen", "Gráficos", "Quiénes respondieron"]
    assert libro["Quiénes respondieron"].max_row == 5  # encabezado + 4 respuestas


def test_significados_por_campana_cambian_motivo_y_sentido(tmp_path):
    import respuestas as R

    df = pd.DataFrame({
        "empresa": ["E", "E", "E"], "difusion": ["Encuesta A", "Encuesta A", "Cobranza"],
        "telefono": ["1", "2", "3"], "leido_en": pd.NaT, "despachado_en": pd.NaT,
        "respuesta": ['{"label_2":["1"]}', '{"satisfaccion":"3"}', "Ya pagué"],
    })
    a = R.analizar(df)
    assert list(a["sentido"]) == [R.NEUTRAL, R.NEUTRAL, R.POSITIVA]
    con = db.conectar(tmp_path / "t.db")
    db.crear_empresa(con, "E")
    db.guardar_significados(con, "E", "ENCUESTA  a", [("Opción 1", "Sin señal", R.NEGATIVA),
                                                     ("Calificación 3", "", R.NEGATIVA)])
    a = R.analizar(df, db.significados(con))
    assert a["motivos"][0] == ["Sin señal"] and list(a["sentido"]) == [R.NEGATIVA, R.NEGATIVA, R.POSITIVA]
    v = R.valores_campana(a, "E", "Encuesta A", db.significados(con)[("E", "encuesta a")])
    assert list(v["Valor"]) == ["Calificación 3", "Opción 1"] and list(v["Significado"]) == ["Calificación 3", "Sin señal"]
    db.borrar_significados(con, "E", "Encuesta A")
    assert db.significados(con) == {}


def test_renombrar_empresa(tmp_path):
    import pytest

    con = db.conectar(tmp_path / "t.db")
    a, b = db.crear_empresa(con, "Tigo"), db.crear_empresa(con, "Viva")
    db.guardar_carga(con, connectly.parse(CSV), "Connectly", a, "a.csv", {})
    with pytest.raises(ValueError):
        db.renombrar_empresa(con, b, "tigo")
    with pytest.raises(ValueError):
        db.renombrar_empresa(con, b, "  ")
    db.renombrar_empresa(con, a, "Tigo  Bolivia")
    r = db.resumen_empresas(con).set_index("nombre")
    assert r.loc["Tigo Bolivia", "mensajes"] == 80 and r.loc["Viva", "mensajes"] == 0


def test_hover_de_un_solo_renglon(tmp_path):
    import graficos
    import respuestas as R

    con = db.conectar(tmp_path / "t.db")
    db.guardar_carga(con, connectly.parse(CSV), "Connectly", db.crear_empresa(con, "E"), "a.csv", {})
    df = reports.con_difusion(db.mensajes(con))
    a = R.analizar(df)
    figuras = graficos.para_campana(df, a)
    assert [g.titulo for g in figuras][:2] == [graficos.TITULOS["embudo"], graficos.TITULOS["resultado_envio"]]
    for g in filter(None, figuras):
        for traza in g.fig.data:
            assert "<br>" not in (traza.hovertemplate or ""), g.titulo



def _dos_campanas(tmp_path):
    """Base con dos campañas: la del CSV y una copia con otro nombre."""
    con = db.conectar(tmp_path / "t.db")
    df = connectly.parse(CSV)
    otra = df.assign(campana=df["campana"].str.replace(r"^\S+", "OTRA", regex=True),
                     session_id=df["session_id"] + "_b")
    db.guardar_carga(con, pd.concat([df, otra], ignore_index=True), "Connectly", db.crear_empresa(con, "E"), "a.csv", {})
    return reports.con_difusion(db.mensajes(con))


def test_informe_de_varias_campanas_sin_graficos(tmp_path):
    from io import BytesIO

    from openpyxl import load_workbook

    df = _dos_campanas(tmp_path)
    assert len(reports.campanas_de(df)) == 2
    assert reports._imagenes(df, reports.SECCIONES) == []
    libro = load_workbook(BytesIO(reports.excel_bytes(df, reports.SECCIONES, {"Filtros": "Ninguno"})))
    assert libro.sheetnames == ["Resumen", "Respuestas por campaña", "Quiénes respondieron"]
    assert reports.pdf_bytes(df, reports.SECCIONES, {"Filtros": "Ninguno"})[:4] == b"%PDF"
    bloques = reports.por_campana_informe(df, reports.SECCIONES)
    assert [b["respondieron"] for b in bloques] == [4, 4]


def test_tabla_de_respuestas_de_una_campana():
    import respuestas as R

    df = pd.DataFrame({
        "empresa": "E", "difusion": "Encuesta A", "telefono": ["1", "2", "3", "4"],
        "leido_en": pd.NaT, "despachado_en": pd.NaT,
        "respuesta": ['{"label_2":["1"]}', '{"label_2":["1","2"]}', '{"satisfaccion":"5"}', "Hola"],
    })
    conf = {"Opción 1": ("Sin señal", R.NEGATIVA)}
    a = R.analizar(df, {("E", "encuesta a"): conf})
    t = R.tabla_campana(a, "E", "Encuesta A", conf).set_index("Respuesta")
    assert t.loc["Sin señal", "Clientes"] == 2 and t.loc["Sin señal", "Sentido"] == R.NEGATIVA
    assert t.loc["Sin señal", "Valor original"] == "Opción 1" and t.loc["Sin señal", "% de los que respondieron"] == "50.0%"
    assert list(t["Sentido"]) == sorted(t["Sentido"], key=R.SENTIDOS.index)


def test_categorias_en_mayusculas_y_dona(tmp_path):
    import sqlite3

    import graficos

    ruta = tmp_path / "t.db"
    con = db.conectar(ruta)
    df = connectly.parse(CSV)
    db.guardar_carga(con, df, "Connectly", db.crear_empresa(con, "E"), "a.csv",
                     {c: {"categoria": "marketing"} for c in df["campana"].unique()})
    # Una base vieja con minúsculas se pasa a mayúsculas al abrirla.
    sqlite3.connect(ruta).execute("UPDATE campanas SET categoria = 'utility'").connection.commit()
    con = db.conectar(ruta)
    assert {c for (c,) in con.execute("SELECT categoria FROM campanas")} == {"UTILITY"}
    t = reports.por_categoria(db.mensajes(con))
    assert list(t["categoria"]) == ["UTILITY", "MARKETING"] and list(t["difusiones"]) == [1, 0]
    g = graficos.categorias(db.mensajes(con))
    assert list(g.fig.data[0].labels) == ["UTILITY"] and "<br>" not in g.fig.data[0].hovertemplate
