"""Páginas: login obligatorio, una empresa a la vez, gráficos solo con campaña elegida, carga de archivos."""
from urllib.parse import urlencode

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from connectly import importador as connectly
from nucleo.models import Carga, Empresa, Mensaje
from nucleo.servicios import cargas, datos
from nucleo.tests import CSV


@override_settings(ALLOWED_HOSTS=["testserver"])
class Paginas(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("ana", password="clave-segura-123")
        self.client.force_login(self.user)
        df = connectly.parse(CSV)
        cargas.guardar(df, "Connectly", Empresa.objects.create(nombre="Tigo"), "a.csv")
        otra = df.assign(session_id=df["session_id"] + "_t")
        cargas.guardar(otra, "Connectly", Empresa.objects.create(nombre="Terbol"), "b.csv")
        self.campana = datos.mensajes()["difusion"].iloc[0]

    def test_login_obligatorio(self):
        self.client.logout()
        for url in ["/", "/informe/", "/campanas/", "/connectly/", "/generador/", "/grafico/embudo/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertTrue(r["Location"].startswith("/ingresar/"), url)
        self.assertEqual(self.client.get("/ingresar/").status_code, 200)

    def test_todas_las_paginas_abren(self):
        for url in ["/", "/informe/", "/campanas/", "/campanas/significados/", "/empresas/", "/historial/",
                    "/connectly/", "/connectly/cargar/", "/generador/", "/empresas/tarifas/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_dashboard_muestra_una_sola_empresa(self):
        r = self.client.get("/?empresa=Terbol")
        self.assertContains(r, "Terbol · Connectly")  # rótulo del encabezado
        self.assertEqual(r.context["kpis"][0]["valor"], "80")  # no suma las 160 de las dos empresas

    def test_graficos_solo_con_campana(self):
        r = self.client.get("/?empresa=Tigo")
        self.assertNotContains(r, "/grafico/embudo/")
        self.assertEqual(self.client.get("/grafico/embudo/?empresa=Tigo").status_code, 404)
        q = urlencode({"empresa": "Tigo", "campana": self.campana})
        r = self.client.get("/?" + q)
        self.assertContains(r, "/grafico/embudo/")
        d = self.client.get("/grafico/embudo/?" + q).json()
        self.assertIn("fig", d)
        self.assertEqual(self.client.get("/grafico/errores/?" + q).status_code, 200)

    def test_clic_en_grafico_filtra_quienes_respondieron(self):
        df = datos.mensajes()
        tipo = datos.respuestas(df[(df["empresa"] == "Tigo") & (df["difusion"] == self.campana)])["tipo"].iloc[0]
        q = urlencode({"empresa": "Tigo", "campana": self.campana, "tipo": tipo})
        r = self.client.get("/respondieron/?" + q)
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.content.decode().count("<tr"), 1)
        r = self.client.get("/respondieron.csv?" + q)
        self.assertEqual(r["Content-Type"], "text/csv")

    def test_informe_y_descargas(self):
        q = urlencode({"empresa": "Tigo", "c": self.campana})
        self.assertContains(self.client.get("/informe/?" + q), "Descargar Excel")
        self.assertEqual(self.client.get("/informe/excel/?" + q).content[:2], b"PK")

    def test_informe_sin_respuestas_de_clientes(self):
        con = urlencode({"empresa": "Tigo", "c": self.campana, "s": ["Resumen general", "Respuestas de clientes"]},
                        doseq=True)
        sin = urlencode({"empresa": "Tigo", "c": self.campana, "s": ["Resumen general"]}, doseq=True)
        self.assertContains(self.client.get("/informe/?" + con), 'id="panel-respuestas"')
        r = self.client.get("/informe/?" + sin)
        self.assertNotContains(r, 'id="panel-respuestas"')
        self.assertContains(r, "no incluye la información de las respuestas")
        from io import BytesIO

        from openpyxl import load_workbook

        hojas = load_workbook(BytesIO(self.client.get("/informe/excel/?" + sin).content)).sheetnames
        self.assertNotIn("Quiénes respondieron", hojas)
        hojas = load_workbook(BytesIO(self.client.get("/informe/excel/?" + con).content)).sheetnames
        self.assertIn("Quiénes respondieron", hojas)

    def test_indicadores_horario_y_mapa_en_dashboard_y_campana(self):
        r = self.client.get("/?empresa=Tigo")
        for texto in ["Indicadores clave", "Calidad de la base", "/grafico/horario_entrega/", "/grafico/mapa_lectura/"]:
            self.assertContains(r, texto)
        self.assertNotContains(r, "CSAT")  # sin campaña elegida no se muestra satisfacción
        for g in ["horario_entrega", "mapa_lectura"]:
            d = self.client.get(f"/grafico/{g}/?empresa=Tigo").json()  # también sin campaña
            self.assertIn("fig", d)
            self.assertNotIn("<br>", d["fig"]["data"][0]["hovertemplate"])
        q = urlencode({"empresa": "Tigo", "campana": self.campana})
        r = self.client.get("/?" + q)
        self.assertContains(r, "Efectividad de gestión")
        embudo = self.client.get("/grafico/embudo/?" + q).json()
        self.assertIn("percentInitial", embudo["fig"]["data"][0]["texttemplate"][-1])  # respuestas sobre enviados

    def test_descargar_numeros_repetidos(self):
        from io import BytesIO

        from openpyxl import load_workbook

        r = self.client.get("/repetidos/?" + urlencode({"empresa": "Tigo", "campana": self.campana}))
        libro = load_workbook(BytesIO(r.content))
        hoja = libro["Números repetidos"]
        self.assertEqual([c.value for c in hoja[1]][:4], ["Número", "Veces", "Campaña", "Envíos"])
        tigo = datos.mensajes().query("empresa == 'Tigo'")
        esperado = int((tigo.groupby(["difusion", "telefono"]).size() > 1).sum())
        self.assertEqual(hoja.max_row - 1, esperado)

    def test_tarifas_por_empresa_y_costo(self):
        from nucleo.models import Tarifa

        r = self.client.post("/empresas/tarifas/", {"empresa": "Tigo", "moneda": "USD", "precio_UTILITY": "0,02",
                                                    "precio_MARKETING": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(str(Tarifa.objects.get(empresa__nombre="Tigo", categoria="UTILITY").precio), "0.02000")
        self.client.post("/empresas/tarifas/", {"empresa": "Terbol", "moneda": "BOB", "precio_UTILITY": "0,10"})
        q = urlencode({"empresa": "Tigo", "campana": self.campana})
        self.assertContains(self.client.get("/?" + q), "Ingresos de Bridge4")
        tigo = self.client.get("/?empresa=Tigo").context["g_ind"]["ind_costo"]
        terbol = self.client.get("/?empresa=Terbol").context["g_ind"]["ind_costo"]
        self.assertNotEqual((tigo["total"], tigo["moneda"]), (terbol["total"], terbol["moneda"]))  # cada empresa, su tarifa
        Tarifa.objects.filter(empresa__nombre="Tigo").delete()
        sin = self.client.get("/?empresa=Tigo").context["g_ind"]["ind_costo"]
        self.assertFalse(sin["disponible"])
        self.assertContains(self.client.get("/?empresa=Tigo"), "Falta el precio de UTILITY")

    def test_ingresos_en_dashboard_y_costos_en_informe(self):
        from io import BytesIO

        from openpyxl import load_workbook

        self.client.post("/empresas/tarifas/", {"empresa": "Tigo", "moneda": "BOB", "precio_UTILITY": "0,01",
                                                "precio_MARKETING": "0,05"})
        # Dashboard (interno): ingresos de Bridge4, sin ROI.
        r = self.client.get("/?empresa=Tigo")
        c = r.context["g_ind"]["ind_ingresos"]
        self.assertEqual(c["campanas_n"], len(c["por_campana"]))
        self.assertContains(r, "Ingresos de las")
        self.assertNotContains(r, "ROI")
        libro = load_workbook(BytesIO(self.client.get("/ingresos.xlsx?empresa=Tigo").content))
        self.assertEqual(libro.sheetnames, ["Por campaña", "Por mes", "Por categoría", "Resumen"])
        self.assertIn("Ingreso (Bs)", [x.value for x in libro["Por campaña"][1]])
        q = urlencode({"empresa": "Tigo", "campana": self.campana})
        self.assertIsNone(self.client.get("/?" + q).context["c_ind"]["ind_ingresos"])  # tabla de todas: solo general
        # Informe (lo recibe la empresa): nunca lleva costos, aunque se pidan por la URL.
        q = urlencode({"empresa": "Tigo", "c": self.campana, "s": ["Resumen general", "Costos"]}, doseq=True)
        self.assertNotContains(self.client.get("/informe/?" + q), "Costos de las campañas")
        self.assertNotContains(self.client.get("/informe/"), 'value="Costos"')
        self.assertNotIn("Costos", load_workbook(BytesIO(self.client.get("/informe/excel/?" + q).content)).sheetnames)

    def test_excel_y_pdf_dicen_cocco_y_no_connectly(self):
        from io import BytesIO

        from openpyxl import load_workbook

        q = urlencode({"empresa": "Tigo", "c": self.campana}, doseq=True)
        libro = load_workbook(BytesIO(self.client.get("/informe/excel/?" + q).content))
        textos = [str(c.value) for h in libro.worksheets for fila in h.iter_rows() for c in fila if c.value]
        self.assertFalse([x for x in textos if "connectly" in x.lower()])
        self.assertIn("Cocco", textos)  # filtro "Plataforma"
        self.assertEqual(len(libro["Gráficos"]._images) > 0, True)  # los gráficos siguen en el Excel
        from nucleo.servicios.analisis import _latin1

        self.assertEqual(_latin1("Plataforma: Connectly"), "Plataforma: Cocco")  # todo el texto del PDF pasa por aquí

    def test_menu_reportes_agrupa_informe_y_html(self):
        for url in ["/informe/", "/generador/"]:
            r = self.client.get(url)
            self.assertContains(r, "Informe (Excel / PDF)")
            self.assertContains(r, 'class="activo" aria-current="page">Reportes<')
        self.assertNotContains(self.client.get("/"), "Cargar S1")

    def test_editar_categoria_de_campana(self):
        c = Empresa.objects.get(nombre="Tigo").campanas.first()
        r = self.client.post("/campanas/?empresa=Tigo", {"id": [c.id], f"cat_{c.id}": "MARKETING",
                                                          f"quien_{c.id}": "Ana", f"fecha_{c.id}": "2026-11-10"})
        self.assertEqual(r.status_code, 302)
        c.refresh_from_db()
        self.assertEqual((c.categoria, c.solicitado_por), ("MARKETING", "Ana"))
        self.assertIn("MARKETING", set(datos.mensajes()["categoria"]))

    def test_subir_reporte_a_mano(self):
        nueva = Empresa.objects.create(nombre="Nueva")
        archivo = SimpleUploadedFile("reporte.csv", CSV.read_bytes(), content_type="text/csv")
        r = self.client.post("/connectly/cargar/", {"accion": "subir", "empresa": nueva.id, "archivo": archivo})
        self.assertEqual(r.status_code, 302)
        r = self.client.get("/connectly/cargar/")
        self.assertContains(r, "Campañas del archivo")
        r = self.client.post("/connectly/cargar/", {"accion": "guardar", "incluir_0": "1", "nombre_0": "",
                                                    "cat_0": "MARKETING", "quien_0": "", "fecha_0": ""})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Mensaje.objects.filter(campana__empresa=nueva).count(), 80)
        self.assertEqual(Carga.objects.filter(empresa=nueva).get().usuario, "ana")

    def test_borrar_todo_pide_confirmacion_y_respalda(self):
        with self.settings(CARPETA_RESPALDOS=self._tmp()):
            self.client.post("/historial/", {"confirmar": "no"})
            self.assertTrue(Mensaje.objects.exists())
            self.client.post("/historial/", {"confirmar": "BORRAR"})
            self.assertFalse(Mensaje.objects.exists())
            self.assertTrue(any(self._carpeta.glob("respaldo_antes_de_borrar_*.json.gz")))

    def _tmp(self):
        import tempfile
        from pathlib import Path

        self._carpeta = Path(tempfile.mkdtemp())
        return self._carpeta
