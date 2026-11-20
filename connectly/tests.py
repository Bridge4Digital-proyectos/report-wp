"""Importador del CSV de la API y sincronización con Connectly (API simulada: no se conecta a internet)."""
import json
from io import BytesIO
from unittest import mock

import pandas as pd
from django.test import TestCase

from connectly import api, importador, sincronizar
from connectly.models import CuentaConnectly
from nucleo.models import Empresa, Mensaje
from nucleo.tests import CSV

COLUMNAS_API = ["customer_external_id", "business_id", "campaign_name", "sendout_id", "cnt_session_id", "sent_at",
                "delivered_at", "read_at", "opt_out_at", "error_code", "error_msg", "button_clicks", "link_clicks",
                "input_variables", "output_variables"]


def csv_api() -> bytes:
    """El CSV de prueba convertido al formato del reporte programado (campaign.daily.v1)."""
    crudo = pd.read_csv(CSV, dtype=str, keep_default_na=False)
    for c in COLUMNAS_API:
        if c not in crudo.columns:
            crudo[c] = ""
    crudo["output_variables"] = [('{"respuesta_cliente": "%s"}' % r.replace('"', "'")) if r else ""
                                 for r in crudo["responses"]]
    return crudo[COLUMNAS_API].to_csv(index=False).encode()


class Importador(TestCase):
    def test_csv_manual(self):
        df = importador.parse(CSV)
        self.assertEqual(len(df), 80)
        self.assertEqual(set(df["categoria_plantilla"].dropna()), {"UTILITY"})
        self.assertEqual((df["respuesta"] != "").sum(), 4)
        fila = df[df["telefono"] == "+59170000014"].iloc[0]
        self.assertEqual((fila["estado"], fila["error_code"]), ("Leído", "131026"))
        self.assertEqual(df[df["telefono"] == "+59170000026"].iloc[0]["estado"], "Fallido")
        self.assertEqual(df[df["telefono"] == "+59170000053"].iloc[0]["estado"], "Enviado")

    def test_csv_de_la_api(self):
        archivo = BytesIO(csv_api())
        archivo.name = "api.csv"
        df = importador.parse(archivo)
        manual = importador.parse(CSV)
        self.assertEqual(len(df), 80)
        self.assertEqual(list(df["estado"]), list(manual["estado"]))
        self.assertEqual((df["respuesta"] != "").sum(), 4)  # vienen de output_variables
        self.assertTrue(df["plantilla"].isna().all())
        self.assertEqual(list(df["despachado_en"]), list(df["enviado_en"]))  # sin dispatched_at

    def test_respuesta_desde_output_variables_como_el_csv_manual(self):
        fila = {"output_variables": '{"respuesta_encuesta": "{\\"aspectos\\":\\"buena_velocidad\\",\\"calificacion\\":\\"4\\"}"}'}
        self.assertEqual(importador._respuesta(fila), "aspectos: buena_velocidad, calificacion: 4")
        lista = '{"problemas":["se_corta"],"satisfaccion":"2"}'
        fila = {"output_variables": json.dumps({"resp_flow": lista, "respuesta_cliente": "Hola"})}
        self.assertEqual(importador._respuesta(fila), lista + " | Hola")  # con listas queda tal cual
        self.assertEqual(importador._respuesta({"output_variables": "", "responses": ""}), "")

    def test_archivo_que_no_es_de_connectly(self):
        archivo = BytesIO(b"a,b\n1,2\n")
        archivo.name = "x.csv"
        with self.assertRaisesRegex(ValueError, "no parece un reporte de Connectly"):
            importador.parse(archivo)


class Sincronizacion(TestCase):
    def setUp(self):
        self.empresa = Empresa.objects.create(nombre="Tigo")
        self.cuenta = CuentaConnectly.objects.create(empresa=self.empresa, business_id="biz-1",
                                                     variable_api_key="CONNECTLY_API_KEY_PRUEBA")
        def rep(nombre, run, tipo="campaign.sessions.v1"):
            return {"id": f"rep-{run}", "name": nombre, "type": tipo, "presignedUrlTtl": "3600s",
                    "lastRun": {"id": run, "status": "completed", "metadata": None,
                                "result": {"url": f"https://firmado/{run}.csv", "createdAt": "2026-11-19T15:56:36Z"}}}

        # Como en la cuenta real: reportes por campaña, diarios de 30 días y de actividad, todos con el mismo createdAt.
        self.respuesta_api = [
            rep("Encuesta Video Shaping 11 11 26", "run-campana"),
            rep("Campaign_Report_-_Ultimos_30_dias_diario_-_2026-11-18", "run-18"),
            rep("Campaign_Report_-_Ultimos_30_dias_diario_-_2026-11-19", "run-19"),
            rep("Activity_TigoGTVDTH_-_2026-11-20", "run-act", "campaign.sessions.activity.v1"),
        ]

    def _descarga(self, url):
        b = BytesIO(csv_api())
        b.name = "connectly_api.csv"
        return b

    @mock.patch.dict("os.environ", {"CONNECTLY_API_KEY_PRUEBA": "clave"})
    def test_no_corren_dos_sincronizaciones_a_la_vez(self):
        from datetime import datetime

        from connectly.models import Sincronizacion as Registro

        Registro.objects.create(cuenta=self.cuenta, inicio=datetime.now(), estado="en_curso")
        with mock.patch.object(api, "reportes") as rep:
            s = sincronizar.cuenta(self.cuenta)
        rep.assert_not_called()
        self.assertEqual(s.detalle, "Ya hay una sincronización en curso.")

    def test_sin_api_key_da_error_claro(self):
        s = sincronizar.cuenta(self.cuenta)
        self.assertEqual(s.estado, "error")
        self.assertIn("CONNECTLY_API_KEY_PRUEBA", s.detalle)

    @mock.patch.dict("os.environ", {"CONNECTLY_API_KEY_PRUEBA": "clave"})
    def test_importa_una_vez_cada_ejecucion(self):
        with mock.patch.object(api, "reportes", return_value=self.respuesta_api) as rep, \
                mock.patch.object(api, "descargar", side_effect=self._descarga):
            s = sincronizar.cuenta(self.cuenta)
            self.assertEqual((s.estado, s.nuevos, s.run_id), ("ok", 80, "run-19"))  # el diario más reciente
            rep.assert_called_with("biz-1", "clave", "campaign.sessions.v1")
            self.assertEqual(Mensaje.objects.count(), 80)
            # La misma ejecución no se vuelve a importar.
            s2 = sincronizar.cuenta(self.cuenta)
            self.assertEqual(s2.estado, "sin_novedad")
            self.assertEqual(Mensaje.objects.count(), 80)
        self.assertEqual(self.empresa.cargas.get().origen, "api")

    @mock.patch.dict("os.environ", {"CONNECTLY_API_KEY_PRUEBA": "clave"})
    def test_reporte_aun_procesando(self):
        for r in self.respuesta_api:
            r["lastRun"]["status"] = "processing"
        with mock.patch.object(api, "reportes", return_value=self.respuesta_api):
            s = sincronizar.cuenta(self.cuenta)
        self.assertEqual(s.estado, "sin_novedad")

    @mock.patch.dict("os.environ", {"CONNECTLY_API_KEY_PRUEBA": "clave"})
    def test_error_de_conexion_queda_registrado(self):
        with mock.patch.object(api, "reportes", side_effect=api.ErrorConnectly("Connectly rechazó la API key")):
            s = sincronizar.cuenta(self.cuenta)
        self.assertEqual((s.estado, s.detalle), ("error", "Connectly rechazó la API key"))

    def test_api_envia_la_clave_en_el_encabezado(self):
        r = mock.Mock(status_code=200, json=lambda: {"data": self.respuesta_api})
        with mock.patch("connectly.api.requests.get", return_value=r) as get:
            elegido = api.ultima_ejecucion("biz-1", "clave", "campaign.sessions.v1",
                                           "Campaign_Report_-_Ultimos_30_dias_diario")
            self.assertEqual((elegido["id"], elegido["nombre"]),
                             ("run-19", "Campaign_Report_-_Ultimos_30_dias_diario_-_2026-11-19"))
        url = get.call_args.args[0]
        self.assertEqual(url, "https://api.connectly.ai/v1/businesses/biz-1/reporting/reports")
        self.assertEqual(get.call_args.kwargs["headers"], {"X-API-Key": "clave"})

    def test_programador_calcula_la_proxima_hora(self):
        from datetime import datetime

        from connectly.management.commands.programador import proxima

        self.assertEqual(proxima("07:00", datetime(2026, 11, 19, 6, 0)), datetime(2026, 11, 19, 7, 0))
        self.assertEqual(proxima("07:00", datetime(2026, 11, 19, 8, 0)), datetime(2026, 11, 20, 7, 0))
