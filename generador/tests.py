import json
import re
from urllib.parse import urlencode

import pandas as pd
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from connectly import importador as connectly
from generador import servicios
from nucleo.models import Empresa
from nucleo.servicios import cargas, datos
from nucleo.tests import CSV


def _detalle(html: str) -> dict:
    return json.loads(re.search(r'<script id="datos-detalle" type="application/json">(.*?)</script>', html, re.S).group(1))


@override_settings(ALLOWED_HOSTS=["testserver"])
class Generador(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user("ana"))
        cargas.guardar(connectly.parse(CSV), "Connectly", Empresa.objects.create(nombre="Tigo"), "a.csv")
        self.df = datos.mensajes()
        self.campana = self.df["difusion"].iloc[0]

    def test_indicadores(self):
        r = servicios.calcular(self.df)
        k = {x["nombre"]: x["valor"] for x in r["kpis"]}
        self.assertEqual(k["Total de contactos"], str(self.df["telefono"].nunique()))
        self.assertEqual(int(k["Mensajes enviados"]), int(self.df["enviado_en"].notna().sum()))
        enviados = int(self.df["enviado_en"].notna().sum())
        self.assertEqual(r["efectividad"]["efectivas"], f"{enviados:,}".replace(",", "."))  # gestión efectiva = enviado
        self.assertEqual(r["efectividad"]["respondieron"], "4")
        # Rechazado (nunca se envió) y fallido (se envió y no llegó) no se mezclan.
        fallido = self.df["estado"] == "Fallido"
        self.assertEqual(int(k["Mensajes rechazados"]), int((fallido & self.df["enviado_en"].isna()).sum()))
        self.assertEqual(int(k["Mensajes fallidos"]), int((fallido & self.df["enviado_en"].notna()).sum()))
        self.assertEqual(len(r["detalle"]["filas"]), 80)
        # Anchos de barra válidos para CSS (con punto) y proporcionales.
        anchos = [float(b["ancho"]) for b in r["embudo"]]
        self.assertEqual(max(anchos), 100.0)
        self.assertTrue(all(0 <= a <= 100 for a in anchos) and min(anchos) < 100)

    def test_efectividad_sobre_enviados_y_secciones_nuevas(self):
        r = servicios.calcular(self.df)
        enviados = int(self.df["enviado_en"].notna().sum())
        self.assertEqual(r["efectividad"]["pct"], f"{enviados / len(self.df):.1%}".replace(".", ","))
        self.assertEqual(r["efectividad"]["pct_respuesta"], f"{4 / enviados:.1%}".replace(".", ","))
        self.assertIn("de enviados", r["embudo"][-1]["pct"])
        self.assertNotIn("segundo", r)  # quitado a pedido del usuario
        self.assertEqual(len(r["horario"]["columnas"]), 24)
        self.assertTrue(r["mapa"]["filas"] and len(r["mapa"]["filas"][0]["celdas"]) == 24)
        self.assertEqual([f["clave"] for f in r["calidad"]["filas"]],
                         ["sin_whatsapp", "bloqueo_meta", "baja_marketing", "otro", "repetidos"])
        self.assertNotIn("costo", r)  # el reporte de la empresa no lleva costos

    def test_reporte_desde_la_base(self):
        q = urlencode({"origen": "base", "empresa": "Tigo", "plataforma": "Connectly", "campana": self.campana})
        r = self.client.get("/generador/reporte/?" + q)
        html = r.content.decode()
        self.assertEqual(r.status_code, 200)
        for texto in ["Efectividad de gestión", "Rechazadas", "Respuesta del cliente", "Horario de entrega",
                      "¿Cuándo leen los clientes?", "Calidad de la base", "Indicadores clave", "Detalle por línea",
                      "data:image/png;base64,"]:
            self.assertIn(texto, html)
        self.assertNotIn("/static/", html)  # autónomo: no depende de archivos del servidor
        self.assertIsNone(re.search(r"width:\d+,\d", html))  # nada de comas decimales en el CSS
        self.assertNotIn("Segundo intento", html)
        self.assertNotIn("Costo estimado</span>", html)  # el costo es opcional y va apagado
        self.assertEqual(len(_detalle(html)["filas"]), 80)
        r = self.client.get("/generador/reporte/?" + q + "&descargar=1")
        self.assertIn("attachment;", r["Content-Disposition"])
        self.assertTrue(r["Content-Disposition"].rstrip('"').endswith(".html"))

    def test_reporte_sin_respuestas_de_clientes(self):
        q = urlencode({"origen": "base", "empresa": "Tigo", "plataforma": "Connectly", "campana": self.campana,
                       "opciones": 1})  # formulario enviado con el interruptor apagado
        html = self.client.get("/generador/reporte/?" + q).content.decode()
        self.assertNotIn("Lo que <em>respondieron</em>", html)
        self.assertIn("Efectividad de gestión", html)  # la efectividad (mensajes enviados) se mantiene
        d = _detalle(html)
        self.assertFalse(d["con_respuestas"])
        self.assertTrue(all(f[6] == "" and f[4] == -1 for f in d["filas"]))  # sin textos ni clasificación
        self.assertEqual(sum(f[7] for f in d["filas"]), 4)
        q2 = q + "&respuestas=1"
        html = self.client.get("/generador/reporte/?" + q2).content.decode()
        self.assertIn("Lo que <em>respondieron</em>", html)
        self.assertTrue(any(f[6] for f in _detalle(html)["filas"]))

    def test_reporte_desde_un_archivo(self):
        self.assertEqual(self.client.get("/generador/").status_code, 200)
        archivo = SimpleUploadedFile("reporte.csv", CSV.read_bytes(), content_type="text/csv")
        r = self.client.post("/generador/", {"archivo": archivo, "empresa_archivo": "Tigo"})
        self.assertEqual(r.status_code, 302)
        r = self.client.get("/generador/")
        self.assertContains(r, "reporte.csv")
        r = self.client.get("/generador/reporte/?" + urlencode({"origen": "archivo", "campana": self.campana}))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Archivo: reporte.csv", r.content.decode())
        self.client.post("/generador/quitar-archivo/")
        self.assertEqual(self.client.get("/generador/reporte/?" + urlencode(
            {"origen": "archivo", "campana": self.campana})).status_code, 404)

    def test_archivo_que_no_es_reporte(self):
        archivo = SimpleUploadedFile("x.csv", b"a,b\n1,2\n", content_type="text/csv")
        r = self.client.post("/generador/", {"archivo": archivo}, follow=True)
        self.assertContains(r, "no parece un reporte de Connectly")

    def test_la_respuesta_del_cliente_no_inyecta_html(self):
        df = self.df.copy()
        df.loc[df.index[0], "respuesta"] = "</script><script>alert(1)</script>"
        html = servicios.calcular(df)
        from django.template.loader import render_to_string

        salida = render_to_string("generador/reporte.html", {**html, "logo": "", "logo_pie": "", "icono": "",
                                                             "origen": "x"})
        self.assertNotIn("<script>alert(1)</script>", salida)


@override_settings(ALLOWED_HOSTS=["testserver"])
class CostoEnReporte(TestCase):
    def setUp(self):
        from nucleo.models import Tarifa

        self.client.force_login(User.objects.create_user("ana"))
        empresa = Empresa.objects.create(nombre="Tigo")
        cargas.guardar(connectly.parse(CSV), "Connectly", empresa, "a.csv")
        Tarifa.objects.create(empresa=empresa, categoria="UTILITY", precio="0.01", moneda="USD")
        self.q = {"origen": "base", "empresa": "Tigo", "plataforma": "Connectly",
                  "campana": datos.mensajes()["difusion"].iloc[0], "opciones": 1, "respuestas": 1}

    def test_el_reporte_de_la_empresa_nunca_lleva_costos(self):
        for extra in ({}, {"costo": 1}):  # aunque se pida por la URL
            html = self.client.get("/generador/reporte/?" + urlencode({**self.q, **extra})).content.decode()
            self.assertNotIn("Costo de la <em>campaña</em>", html)
            self.assertNotIn("Costo total", html)
        self.assertNotContains(self.client.get("/generador/"), 'name="costo"')

    def test_la_plataforma_se_llama_cocco(self):
        import re as _re

        html = self.client.get("/generador/reporte/?" + urlencode(self.q)).content.decode()
        visible = _re.sub(r"data:[^\"')]+", "", html)  # sin imágenes ni fuentes incrustadas
        self.assertNotIn("connectly", visible.lower())
        self.assertIn("<b>Plataforma:</b> Cocco", html)

    def test_repetidos_en_el_reporte(self):
        html = self.client.get("/generador/reporte/?" + urlencode(self.q)).content.decode()
        d = _detalle(html)
        self.assertIn("repetidos", d)
        self.assertEqual(len(d["repetidos"]), int((datos.mensajes().groupby(["difusion", "telefono"]).size() > 1).sum()))
