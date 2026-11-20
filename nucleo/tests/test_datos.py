"""Guardado sin duplicar, informes, significados, empresas y gráficos sobre la base de Django."""
from io import BytesIO

import pandas as pd
from django.test import TestCase
from openpyxl import load_workbook

from connectly import importador as connectly
from nucleo.models import Campana, Empresa
from nucleo.servicios import analisis as reports
from nucleo.servicios import cargas, datos, graficos
from nucleo.servicios import respuestas as R
from nucleo.tests import CSV


def _guardar(nombre="E", df=None, info=None):
    empresa, _ = Empresa.objects.get_or_create(nombre=nombre)
    df = connectly.parse(CSV) if df is None else df
    return empresa, df, cargas.guardar(df, "Connectly", empresa, "a.csv", info or {})


class Cargas(TestCase):
    def test_guardar_sin_duplicar_y_exportar(self):
        df = connectly.parse(CSV)
        info = {c: {"categoria": "utility", "solicitado_por": "Ana", "fecha_solicitud": "2026-11-10"}
                for c in df["campana"].unique()}
        empresa, df, cuenta = _guardar("Empresa prueba", df, info)
        self.assertEqual(cuenta, (len(df), 0, 0))
        comp = cargas.comparar(df, "Connectly", empresa)
        self.assertEqual(comp["sin_cambios"].sum(), len(df))
        self.assertEqual(comp[["nuevas", "actualizadas"]].sum().sum(), 0)
        self.assertEqual(cargas.guardar(df, "Connectly", empresa, "a.csv", info), (0, 0, len(df)))

        mensajes = datos.mensajes()
        self.assertEqual(len(mensajes), len(df))
        k = reports.kpis(mensajes)
        self.assertEqual(k["Total mensajes"][0], len(df))
        self.assertEqual(k["Respuestas"][0], 4)
        self.assertEqual(set(Campana.objects.values_list("categoria", flat=True)), {"UTILITY"})
        filtros = {"Empresa": "Empresa prueba"}
        self.assertEqual(reports.excel_bytes(mensajes, reports.SECCIONES, filtros)[:2], b"PK")
        self.assertEqual(reports.pdf_bytes(mensajes, reports.SECCIONES, filtros)[:4], b"%PDF")

    def test_reporte_mas_reciente_actualiza_sin_borrar(self):
        empresa, viejo, _ = _guardar()
        nuevo = viejo.copy()
        sin_resp = nuevo.index[nuevo["respuesta"] == ""][:3]
        nuevo.loc[sin_resp, "respuesta"] = "Gracias"
        sin_leer = nuevo.index[nuevo["leido_en"].isna() & nuevo["entregado_en"].notna()][:2]
        nuevo.loc[sin_leer, "leido_en"] = "2026-11-12 10:00:00"

        comp = cargas.comparar(nuevo, "Connectly", empresa)
        self.assertEqual(comp["respuestas"].sum(), 3)
        self.assertEqual(comp["leidos"].sum(), 2)
        self.assertEqual(comp["nuevas"].sum(), 0)
        actualizadas = len(set(sin_resp) | set(sin_leer))
        self.assertEqual(comp["actualizadas"].sum(), actualizadas)
        self.assertEqual(cargas.guardar(nuevo, "Connectly", empresa, "nuevo.csv"),
                         (0, actualizadas, len(viejo) - actualizadas))
        k = reports.kpis(datos.mensajes())
        self.assertEqual(k["Respuestas"][0], 7)
        # Si después se sube el reporte viejo, no se pierde nada.
        cargas.guardar(viejo, "Connectly", empresa, "viejo.csv")
        k2 = reports.kpis(datos.mensajes())
        self.assertEqual((k2["Respuestas"][0], k2["Leídos"][0]), (7, k["Leídos"][0]))

    def test_informe_por_campana_con_pruebas(self):
        _guardar()
        t = reports.informe_campanas(datos.mensajes())
        self.assertEqual(len(t), 1)
        f = t.iloc[0]
        self.assertEqual((f["total"], f["mensajes_lote"], f["pruebas"], f["mensajes_prueba"]), (80, 77, 1, 3))
        self.assertEqual(list(reports.secciones(datos.mensajes(), reports.SECCIONES)), reports.TABLAS)

    def test_excel_de_una_campana_tiene_tres_hojas(self):
        _guardar()
        libro = load_workbook(BytesIO(reports.excel_bytes(datos.mensajes(), reports.SECCIONES, {"Filtros": "Ninguno"})))
        self.assertEqual(libro.sheetnames, ["Resumen", "Gráficos", "Quiénes respondieron"])
        self.assertEqual(libro["Quiénes respondieron"].max_row, 5)  # encabezado + 4 respuestas

    def test_informe_de_varias_campanas_sin_graficos(self):
        df = connectly.parse(CSV)
        otra = df.assign(campana=df["campana"].str.replace(r"^\S+", "OTRA", regex=True),
                         session_id=df["session_id"] + "_b")
        _guardar("E", pd.concat([df, otra], ignore_index=True))
        d = datos.mensajes()
        self.assertEqual(len(reports.campanas_de(d)), 2)
        self.assertEqual(reports._imagenes(d, reports.SECCIONES), [])
        libro = load_workbook(BytesIO(reports.excel_bytes(d, reports.SECCIONES, {"Filtros": "Ninguno"})))
        self.assertEqual(libro.sheetnames, ["Resumen", "Respuestas por campaña", "Quiénes respondieron"])
        self.assertEqual(reports.pdf_bytes(d, reports.SECCIONES, {"Filtros": "Ninguno"})[:4], b"%PDF")
        self.assertEqual([b["respondieron"] for b in reports.por_campana_informe(d, reports.SECCIONES)], [4, 4])

    def test_la_cache_ve_los_cambios(self):
        _guardar()
        self.assertEqual(len(datos.mensajes()), 80)
        Campana.objects.update(categoria="MARKETING")
        datos.cambiaron()
        self.assertEqual(set(datos.mensajes()["categoria"]), {"MARKETING"})


class SignificadosYEmpresas(TestCase):
    def test_significados_por_campana_cambian_motivo_y_sentido(self):
        df = pd.DataFrame({
            "empresa": ["E", "E", "E"], "difusion": ["Encuesta A", "Encuesta A", "Cobranza"],
            "telefono": ["1", "2", "3"], "leido_en": pd.NaT, "despachado_en": pd.NaT,
            "respuesta": ['{"label_2":["1"]}', '{"satisfaccion":"3"}', "Ya pagué"],
        })
        self.assertEqual(list(R.analizar(df)["sentido"]), [R.NEUTRAL, R.NEUTRAL, R.POSITIVA])
        Empresa.objects.create(nombre="E")
        datos.guardar_significados("E", "ENCUESTA  a", [("Opción 1", "Sin señal", R.NEGATIVA),
                                                         ("Calificación 3", "", R.NEGATIVA)])
        a = R.analizar(df, datos.significados())
        self.assertEqual(a["motivos"][0], ["Sin señal"])
        self.assertEqual(list(a["sentido"]), [R.NEGATIVA, R.NEGATIVA, R.POSITIVA])
        v = R.valores_campana(a, "E", "Encuesta A", datos.significados()[("E", "encuesta a")])
        self.assertEqual(list(v["Valor"]), ["Calificación 3", "Opción 1"])
        self.assertEqual(list(v["Significado"]), ["Calificación 3", "Sin señal"])
        datos.borrar_significados("E", "Encuesta A")
        self.assertEqual(datos.significados(), {})

    def test_resumen_de_empresas(self):
        _guardar("Tigo")
        Empresa.objects.create(nombre="Viva")
        r = {e["nombre"]: e for e in datos.resumen_empresas()}
        self.assertEqual((r["Tigo"]["mensajes"], r["Viva"]["mensajes"]), (80, 0))


class Graficos(TestCase):
    def test_hover_de_un_solo_renglon(self):
        _guardar()
        df = datos.mensajes()
        figuras = graficos.para_campana(df, R.analizar(df))
        self.assertEqual([g.titulo for g in figuras][:2], [graficos.TITULOS["embudo"], graficos.TITULOS["resultado_envio"]])
        for g in figuras:
            for traza in g.fig.data:
                self.assertNotIn("<br>", traza.hovertemplate or "", g.titulo)

    def test_categorias_en_mayusculas_y_dona(self):
        df = connectly.parse(CSV)
        _guardar("E", df, {c: {"categoria": "marketing"} for c in df["campana"].unique()})
        self.assertEqual(set(Campana.objects.values_list("categoria", flat=True)), {"MARKETING"})
        t = reports.por_categoria(datos.mensajes())
        self.assertEqual(list(t["categoria"]), ["UTILITY", "MARKETING"])
        self.assertEqual(list(t["difusiones"]), [0, 1])
        g = graficos.categorias(datos.mensajes())
        self.assertEqual(list(g.fig.data[0].labels), ["MARKETING"])
        self.assertNotIn("<br>", g.fig.data[0].hovertemplate)


class CategoriaMarketingLite(TestCase):
    def test_marketing_lite_cuenta_como_marketing(self):
        from decimal import Decimal

        from nucleo.models import Tarifa
        from nucleo.servicios import indicadores as I

        df = connectly.parse(CSV).assign(categoria_plantilla="MARKETING_LITE")
        empresa, _, _ = _guardar("E", df)
        self.assertEqual(set(Campana.objects.values_list("categoria", flat=True)), {"MARKETING"})
        c = Campana.objects.first()
        c.categoria = "marketing_lite"
        c.save()
        c.refresh_from_db()
        self.assertEqual(c.categoria, "MARKETING")
        # El costo usa la tarifa de MARKETING (no pide una tarifa aparte).
        Tarifa.objects.create(empresa=empresa, categoria="MARKETING", precio=Decimal("0.05"), moneda="USD")
        costo = I.calcular(datos.mensajes(), None, I.tarifas_de("E"))["costo"]
        self.assertTrue(costo["disponible"])
