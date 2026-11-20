import pandas as pd
import pytest

import db
import reports
import respuestas as R
from importers import s1

COLUMNAS = ["Fecha Programada", "Fecha de Envío", "Difusión", "Canal", "Destino", "Caso ID", "Asunto",
            "Plantilla", "Estado de Envío", "Estado de Entrega", "Fecha de Entrega", "Código de Error",
            "Mensaje de Error", "Parámetros Extra", "Usuario ID"]


def _fila(difusion, destino, envio, entrega, caso="", error=""):
    return ["2026-11-04 15:30:00", "2026-11-04 15:30:04", difusion, "whatsapp", destino, caso, "",
            "plantilla_x", envio, entrega, "2026-11-04 15:49:23" if entrega else "", "0", error, "{}", "10011"]


@pytest.fixture
def archivo(tmp_path):
    filas = [
        _fila("promo_03112026_lote1", "59170000001", "SENT_STATUS_SENT", "DELIVERY_STATUS_READ", caso="58196"),
        _fila("promo_03112026_lote1", "59170000002", "SENT_STATUS_SENT", "DELIVERY_STATUS_DELIVERED"),
        _fila("promo_03112026_lote1", "59170000003", "SENT_STATUS_SENT", "DELIVERY_STATUS_PENDING"),
        _fila("promo_03112026_lote1", "59170000004", "SENT_STATUS_SENT", "DELIVERY_STATUS_FAILURE",
              error="Message undeliverable"),
        _fila("promo_03112026_Prueba", "59170000005", "SENT_STATUS_FAILURE", "", error="(#100) Param"),
        _fila("otra_region_LOTE 2", "59170000006", "SENT_STATUS_SENT", "DELIVERY_STATUS_READ"),
    ]
    ruta = tmp_path / "Detalle de Difusiones.xlsx"
    pd.DataFrame(filas, columns=COLUMNAS).to_excel(ruta, index=False)
    return ruta


def test_parse_s1(archivo):
    df = s1.parse(archivo)
    assert len(df) == 6
    assert set(df["campana"]) == {"promo_03112026 . lote1", "promo_03112026 . Prueba", "otra_region . LOTE 2"}
    por_tel = df.set_index("telefono")
    assert list(por_tel["estado"]) == ["Leído", "Entregado", "Enviado", "Fallido", "Fallido", "Leído"]
    assert por_tel.loc["59170000004", "error_code"] == "S1_FALLA_ENTREGA"
    assert por_tel.loc["59170000004", "error_msg"] == "Message undeliverable"
    assert por_tel.loc["59170000005", "error_code"] == "S1_FALLA_ENVIO"
    assert por_tel.loc["59170000001", "respuesta"] == "Abrió caso N° 58196"
    assert R.interpretar(por_tel.loc["59170000001", "respuesta"])["tipo"] == "Abrió un caso en S1"
    assert (df["respuesta"] != "").sum() == 1
    grupos = reports.agrupar_campanas(df["campana"].unique())
    assert set(grupos.values()) == {"promo_03112026", "otra_region"}


def test_columnas_sin_tildes_y_csv(tmp_path, archivo):
    crudo = pd.read_excel(archivo, dtype=str)
    crudo.columns = [c.replace("í", "i").replace("ó", "o").upper() for c in crudo.columns]
    ruta = tmp_path / "s1.csv"
    crudo.to_csv(ruta, index=False)
    assert len(s1.parse(ruta)) == 6


def test_archivo_que_no_es_de_s1(tmp_path):
    ruta = tmp_path / "otro.csv"
    pd.DataFrame({"a": [1]}).to_csv(ruta, index=False)
    with pytest.raises(ValueError, match="Detalle de Difusiones"):
        s1.parse(ruta)


def test_guardar_s1_sin_duplicar(tmp_path, archivo):
    con = db.conectar(tmp_path / "t.db")
    empresa = db.crear_empresa(con, "Terbol")
    df = s1.parse(archivo)
    assert db.guardar_carga(con, df, "S1", empresa, "a.xlsx", {}) == (6, 0, 0)
    assert db.guardar_carga(con, s1.parse(archivo), "S1", empresa, "a.xlsx", {}) == (0, 0, 6)
    resumen = reports.por_difusion(db.mensajes(con))
    assert set(resumen["difusion"]) == {"promo_03112026", "otra_region"}
    fila = resumen[resumen["difusion"] == "promo_03112026"].iloc[0]
    assert fila["partes"] == 2 and fila["respuestas"] == 1


def test_fechas_de_connectly_y_s1_conviven(tmp_path, archivo):
    """Connectly trae microsegundos y S1 no: ninguna fecha debe perderse al leer la base."""
    from pathlib import Path

    from importers import connectly

    con = db.conectar(tmp_path / "t.db")
    csv = Path(__file__).parent / "fixtures" / "TRABAJO_PROGRAMADO_12_11_26.csv"
    db.guardar_carga(con, connectly.parse(csv), "Connectly", db.crear_empresa(con, "Tigo"), "a.csv", {})
    db.guardar_carga(con, s1.parse(archivo), "S1", db.crear_empresa(con, "Terbol"), "b.xlsx", {})
    m = db.mensajes(con)
    t = m[m["empresa"] == "Terbol"]
    assert t["leido_en"].notna().sum() == 2 and t["despachado_en"].notna().all()
    assert m[m["empresa"] == "Tigo"]["despachado_en"].notna().all()
