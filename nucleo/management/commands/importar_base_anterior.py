"""Copia los datos de la app anterior (Streamlit + SQLite, data/reportes.db) a la base de Django."""
import sqlite3
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from nucleo.models import Campana, Carga, Empresa, Mensaje, Significado
from nucleo.servicios import datos
from nucleo.servicios.cargas import _fecha

COLUMNAS = ["telefono", "session_id", "despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en",
            "error_code", "error_msg", "estado", "respuesta", "clics_boton", "clics_link", "plantilla"]
FECHAS = {"despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en"}


class Command(BaseCommand):
    help = "Importa empresas, campañas, mensajes, historial y significados de data/reportes.db (app anterior)."

    def add_arguments(self, parser):
        parser.add_argument("ruta", nargs="?", default="data/reportes.db")
        parser.add_argument("--reemplazar", action="store_true",
                            help="Borra antes los datos de Django (si no, se niega cuando ya hay datos).")

    def handle(self, *args, ruta, reemplazar=False, **opciones):
        viejo = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)  # solo lectura: la base anterior no se toca
        if Empresa.objects.exists() and not reemplazar:
            raise CommandError("La base de Django ya tiene datos. Usa --reemplazar para borrarlos e importar de nuevo.")
        with transaction.atomic():
            if reemplazar:
                for modelo in (Significado, Mensaje, Carga, Campana, Empresa):
                    modelo.objects.all().delete()
            empresas = {i: Empresa.objects.create(nombre=n) for i, n in viejo.execute("SELECT id, nombre FROM empresas")}
            campanas = {}
            for i, plat, nombre, eid, cat, quien, fecha in viejo.execute(
                    "SELECT id, plataforma, nombre, empresa_id, categoria, solicitado_por, fecha_solicitud FROM campanas"):
                campanas[i] = Campana.objects.create(
                    plataforma=plat, nombre=nombre, empresa=empresas[eid], categoria=(cat or "UTILITY").upper(),
                    solicitado_por=quien or None, fecha_solicitud=fecha or None).id
            lote = []
            cursor = viejo.execute(f"SELECT campana_id, {', '.join(COLUMNAS)} FROM mensajes")
            for fila in cursor:
                valores = dict(zip(COLUMNAS, fila[1:]))
                for c in FECHAS:
                    valores[c] = _fecha(valores[c])
                valores["respuesta"] = valores["respuesta"] or ""
                valores["clics_boton"] = valores["clics_boton"] or 0
                valores["clics_link"] = valores["clics_link"] or 0
                lote.append(Mensaje(campana_id=campanas[fila[0]], **valores))
                if len(lote) >= 5000:
                    Mensaje.objects.bulk_create(lote)
                    lote = []
            Mensaje.objects.bulk_create(lote)
            for archivo, plat, eid, fecha, nuevas, dup, act in viejo.execute(
                    "SELECT archivo, plataforma, empresa_id, fecha_carga, filas_nuevas, filas_duplicadas, "
                    "COALESCE(filas_actualizadas, 0) FROM cargas"):
                Carga.objects.create(archivo=archivo or "", plataforma=plat, empresa=empresas[eid], origen="migracion",
                                     fecha_carga=_fecha(fecha) or datetime.now(), filas_nuevas=nuevas or 0,
                                     filas_duplicadas=dup or 0, filas_actualizadas=act or 0)
            for eid, difusion, valor, significado, sentido in viejo.execute(
                    "SELECT empresa_id, difusion, valor, significado, sentido FROM significados"):
                Significado.objects.create(empresa=empresas[eid], difusion=difusion, valor=valor,
                                           significado=significado or "", sentido=sentido)
            datos.cambiaron()

        # Verificación: mismos totales por empresa que en la base anterior.
        for eid, nombre, total, leidos, fallidos, respuestas in viejo.execute(
                "SELECT e.id, e.nombre, COUNT(m.id), COUNT(m.leido_en), SUM(m.estado = 'Fallido'), "
                "SUM(COALESCE(m.respuesta, '') <> '') FROM empresas e JOIN campanas c ON c.empresa_id = e.id "
                "JOIN mensajes m ON m.campana_id = c.id GROUP BY e.id"):
            q = Mensaje.objects.filter(campana__empresa=empresas[eid])
            nuevo = (q.count(), q.exclude(leido_en=None).count(), q.filter(estado="Fallido").count(),
                     q.exclude(respuesta="").count())
            igual = nuevo == (total, leidos, fallidos, respuestas)
            estilo = self.style.SUCCESS if igual else self.style.ERROR
            self.stdout.write(estilo(f"{nombre}: {nuevo[0]:,} mensajes, {nuevo[1]:,} leídos, {nuevo[2]:,} fallidos, "
                                     f"{nuevo[3]:,} respuestas " + ("(igual que antes)" if igual else
                                                                     f"(antes: {total}, {leidos}, {fallidos}, {respuestas})")))
            if not igual:
                raise CommandError("Los totales no coinciden; revisa la importación.")
