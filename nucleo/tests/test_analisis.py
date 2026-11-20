"""Funciones de análisis puras (sin base de datos): nombres de campañas, meses, respuestas."""
import pandas as pd
from django.test import SimpleTestCase

from nucleo.servicios import analisis as reports
from nucleo.servicios import respuestas as R


class NombresDeCampana(SimpleTestCase):
    def test_lote_y_prueba_forman_una_campana(self):
        self.assertEqual(reports.difusion("Gdv . Trabajo Programado 12 11 26 . Lote 001"), "Gdv . Trabajo Programado")
        self.assertEqual(reports.difusion("Gdv . TRABAJO PROGRAMADO 12 11 26 . Prueba 001"), "Gdv . TRABAJO PROGRAMADO")
        self.assertEqual(reports.difusion("Gdv . Trabajo Programado 12 11 26 . Reenvio"), "Gdv . Trabajo Programado")
        self.assertEqual(reports.difusion("Campaña sin tramos"), "Campaña sin tramos")

    def test_fecha_final_no_separa_la_campana(self):
        a = "Gdv 2611 . 007 . Encuesta Internet Fijo 11 11 26 . Lote 001"
        b = "Gdv 2611 . 007 . ENCUESTA INTERNET FIJO 09 11 26 . Prueba 001"
        self.assertEqual(reports.difusion(a).casefold(), reports.difusion(b).casefold())

    def test_punto_sin_espacio_antes_del_lote(self):
        n = "Gdv 2611 . 008 . Encuesta Post Cambio De Modem 30 10 26. Lote 002"
        self.assertEqual(reports.difusion(n), "Gdv 2611 . 008 . Encuesta Post Cambio De Modem")
        self.assertEqual(reports.renombrar_envio(n, "Encuesta Modem"), "Encuesta Modem . Lote 002")

    def test_etiqueta_y_orden_de_meses(self):
        fechas = pd.Series(pd.to_datetime(["2026-11-03", "2026-01-20", None, "2026-11-30"]))
        self.assertEqual(list(reports.etiqueta_mes(fechas)), ["Noviembre 2026", "Enero 2026", "", "Noviembre 2026"])
        self.assertEqual(reports.meses_ordenados(fechas), ["Noviembre 2026", "Enero 2026"])


class Respuestas(SimpleTestCase):
    def test_interpretar_formatos_de_respuesta(self):
        r = R.interpretar('{"aspectos_neutrales":[],"aspectos_positivos":["buena_cobertura"],"problemas":[],"satisfaccion":"4"}')
        self.assertEqual((r["tipo"], r["calificacion"], r["motivos"]), (R.ENCUESTA, 4, [("Buena cobertura", R.POSITIVO)]))
        r = R.interpretar("calificacion: 2, problemas: otros, problemas_otros: se corta, y es lento")
        self.assertEqual((r["calificacion"], r["motivos"], r["comentario"]),
                         (2, [("Otro motivo", R.NEUTRAL)], "se corta, y es lento"))
        r = R.interpretar('{"rating":"3","razones":["internet_lento"],"sentimiento":"negativo"}')
        self.assertEqual((r["calificacion"], r["motivos"]), (3, [("Internet lento", R.PROBLEMA)]))
        r = R.interpretar('{"label_2":["1","5"],"otro_motivo":"Internet inestable "}')
        self.assertEqual([m for m, _ in r["motivos"]], ["Opción 1", "Opción 5"])
        self.assertEqual(r["comentario"], "Internet inestable")
        r = R.interpretar("Buenas noche | aspectos: buena_velocidad, calificacion: 5")
        self.assertEqual((r["tipo"], r["calificacion"]), (R.ENCUESTA, 5))
        self.assertEqual(R.interpretar("Hola")["tipo"], "Saludo")
        self.assertEqual(R.interpretar("Ya pagué")["tipo"], "Dice que ya pagó")
        self.assertEqual(R.interpretar("This message (type: sticker) is currently unsupported.")["tipo"],
                         "Sticker, emoji o multimedia")

    def test_tabla_de_respuestas_de_una_campana(self):
        df = pd.DataFrame({
            "empresa": "E", "difusion": "Encuesta A", "telefono": ["1", "2", "3", "4"],
            "leido_en": pd.NaT, "despachado_en": pd.NaT,
            "respuesta": ['{"label_2":["1"]}', '{"label_2":["1","2"]}', '{"satisfaccion":"5"}', "Hola"],
        })
        conf = {"Opción 1": ("Sin señal", R.NEGATIVA)}
        a = R.analizar(df, {("E", "encuesta a"): conf})
        t = R.tabla_campana(a, "E", "Encuesta A", conf).set_index("Respuesta")
        self.assertEqual(t.loc["Sin señal", "Clientes"], 2)
        self.assertEqual(t.loc["Sin señal", "Sentido"], R.NEGATIVA)
        self.assertEqual(t.loc["Sin señal", "Valor original"], "Opción 1")
        self.assertEqual(t.loc["Sin señal", "% de los que respondieron"], "50.0%")
        self.assertEqual(list(t["Sentido"]), sorted(t["Sentido"], key=R.SENTIDOS.index))
