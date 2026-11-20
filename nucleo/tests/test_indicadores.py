"""Indicadores clave (sin base de datos): tasas sobre enviados, tiempos, clics, calidad de base, mapa y costo."""
from decimal import Decimal

import pandas as pd
from django.test import SimpleTestCase

from nucleo.servicios import indicadores as I
from nucleo.servicios import respuestas as R


def _df():
    t = pd.Timestamp("2026-11-05 18:00")
    filas = [
        # telefono, enviado, entregado (+s), leido (+min), estado, code, msg, respuesta, clic_b, clic_l, categoria
        ("1", t, 2, 10, "Leído", None, None, "Hola", 1, 0, "UTILITY"),
        ("2", t, 2, 90, "Leído", None, None, "", 0, 1, "UTILITY"),
        ("3", t, 5, None, "Entregado", None, None, "", 0, 0, "UTILITY"),
        ("4", None, None, None, "Fallido", "131026", "Message undeliverable", "", 0, 0, "UTILITY"),
        ("5", t, None, None, "Fallido", "130472", "User's number is part of an experiment", "", 0, 0, "MARKETING"),
        ("6", t, None, None, "Fallido", "S1_FALLA_ENTREGA",
         "This message was not delivered to maintain healthy ecosystem engagement.", "", 0, 0, "MARKETING"),
        ("7", t, None, None, "Fallido", "131050", "Unable to deliver the message. This recipient has chosen to stop "
                                                  "receiving marketing messages", "", 0, 0, "MARKETING"),
        ("1", t, 3, None, "Entregado", None, None, "", 0, 0, "UTILITY"),  # número repetido
    ]
    d = pd.DataFrame(filas, columns=["telefono", "enviado_en", "s", "m", "estado", "error_code", "error_msg",
                                     "respuesta", "clics_boton", "clics_link", "categoria"])
    d["entregado_en"] = d["enviado_en"] + pd.to_timedelta(d["s"], unit="s")
    d["leido_en"] = d["entregado_en"] + pd.to_timedelta(d["m"], unit="min")
    d["despachado_en"] = d["enviado_en"]
    d["difusion"], d["campana"], d["empresa"] = "C", "C . Lote 001", "E"
    return d.drop(columns=["s", "m"])


class Indicadores(SimpleTestCase):
    def test_tasas_sobre_enviados_tiempos_y_clics(self):
        i = I.calcular(_df())
        self.assertEqual((i["enviados"], i["entregados"], i["leidos"], i["respondieron"]), (7, 4, 2, 1))
        self.assertAlmostEqual(i["efectividad"], 7 / 8)  # gestión efectiva = mensaje ENVIADO, sobre la base
        self.assertAlmostEqual(i["tasa_respuesta"], 1 / 7)  # respuestas, aparte, sobre los enviados
        self.assertAlmostEqual(i["tasa_entrega"], 4 / 7)
        self.assertAlmostEqual(i["tasa_lectura"], 2 / 4)
        self.assertAlmostEqual(i["ctr"], 2 / 4)
        self.assertAlmostEqual(i["lectura_1h"], 1 / 2)
        self.assertEqual(i["hora_pico_lectura"], 18)
        self.assertEqual(I.tarjetas(i)[0]["nombre"], "Efectividad de gestión")

    def test_calidad_de_la_base(self):
        c = {f["clave"]: f["n"] for f in I.calidad(_df())["filas"]}
        self.assertEqual(c, {"sin_whatsapp": 1, "bloqueo_meta": 2, "baja_marketing": 1, "otro": 0, "repetidos": 1})
        rep = I.repetidos(_df())
        self.assertEqual(list(rep["Número"]), ["1"])
        self.assertEqual(int(rep["Veces"].iloc[0]), 2)
        # El mismo número en OTRA campaña no es un repetido.
        otra = _df()
        otra.loc[otra.index[-1], "difusion"] = "Otra campaña"
        self.assertEqual(len(I.repetidos(otra)), 0)
        self.assertEqual({f["clave"]: f["n"] for f in I.calidad(otra)["filas"]}["repetidos"], 0)

    def test_horario_y_mapa(self):
        h = I.horario(_df())
        self.assertEqual((len(h["entregas"]), h["pico"], h["total"]), (24, 18, 4))
        m = I.mapa_lectura(_df())
        self.assertEqual((m["modo"], len(m["filas"]), len(m["valores"][0])), ("fecha", 1, 24))
        largo = _df()
        largo.loc[1, "leido_en"] = pd.Timestamp("2026-12-10 09:00")  # más de 14 días: por día de la semana
        self.assertEqual(I.mapa_lectura(largo)["filas"], I.DIAS)

    def test_satisfaccion_solo_si_hay_datos(self):
        sin_encuesta = pd.DataFrame({"calificacion": pd.Series([pd.NA], dtype="Int64"), "sentido": [R.NEUTRAL]})
        self.assertIsNone(I.satisfaccion(sin_encuesta))  # campaña sin flujo ni calificación
        a = pd.DataFrame({"calificacion": pd.Series([5, 4, 2, pd.NA], dtype="Int64"),
                          "sentido": [R.POSITIVA, R.POSITIVA, R.NEGATIVA, R.NEUTRAL]})
        s = I.satisfaccion(a)
        self.assertAlmostEqual(s["csat"], 2 / 3)
        self.assertAlmostEqual(s["sentimiento_neto"], (2 - 1) / 4)

    def test_costo_por_empresa(self):
        d = _df()
        self.assertFalse(I.costo(d, {}, respondieron=1)["disponible"])
        falta = I.costo(d, {"MARKETING": (Decimal("0.05"), "USD")}, respondieron=1)
        self.assertEqual(falta["faltan"], ["UTILITY"])  # los entregados son UTILITY
        a = I.costo(d, {"UTILITY": (Decimal("0.01"), "USD")}, respondieron=1)
        b = I.costo(d, {"UTILITY": (Decimal("0.03"), "USD")}, respondieron=1)
        self.assertAlmostEqual(a["total"], 0.04)
        self.assertAlmostEqual(b["por_respuesta"], 0.12)


class Montos(SimpleTestCase):
    def test_montos_por_campana_mes_y_categoria(self):
        d = _df()
        otra = d.assign(difusion="D", telefono=d["telefono"] + "x")
        todo = pd.concat([d, otra], ignore_index=True)
        tarifas = {"UTILITY": (Decimal("0.10"), "BOB"), "MARKETING": (Decimal("0.50"), "BOB")}
        m = I.montos_detalle(todo, tarifas)
        fila = m["por_campana"].set_index("difusion").loc["C"]
        self.assertAlmostEqual(fila["monto"], 0.40)  # 4 entregados UTILITY × 0,10
        self.assertAlmostEqual(fila["por_respuesta"], 0.40)  # 1 respuesta
        self.assertAlmostEqual(fila["por_leido"], 0.20)  # 2 leídos
        self.assertAlmostEqual(m["total"], 0.80)
        self.assertEqual((m["campanas"], m["moneda"]), (2, "Bs"))
        self.assertNotIn("roi", m["por_campana"])
        self.assertEqual(list(m["por_mes"]["mes"]), ["Noviembre 2026"])
        self.assertIsNone(I.montos_detalle(todo, {"MARKETING": (Decimal("0.5"), "BOB")}))  # falta UTILITY

    def test_costo_por_resultado(self):
        c = I.costo(_df(), {"UTILITY": (Decimal("0.10"), "USD")}, leidos=2, respondieron=1, clics=2)
        self.assertAlmostEqual(c["total"], 0.40)
        self.assertAlmostEqual(c["por_entregado"], 0.10)
        self.assertAlmostEqual(c["por_leido"], 0.20)
        self.assertAlmostEqual(c["por_respuesta"], 0.40)
        self.assertAlmostEqual(c["por_clic"], 0.20)
        self.assertNotIn("roi", c)
