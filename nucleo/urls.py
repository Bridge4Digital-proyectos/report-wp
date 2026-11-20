from django.urls import path

from nucleo.views import paginas, tablero

urlpatterns = [
    path("", tablero.dashboard, name="dashboard"),
    path("grafico/<str:nombre>/", tablero.grafico, name="grafico"),
    path("respondieron/", tablero.respondieron, name="respondieron"),
    path("respondieron.csv", tablero.respondieron_csv, name="respondieron_csv"),
    path("repetidos/", tablero.repetidos, name="repetidos"),
    path("ingresos.xlsx", tablero.ingresos_excel, name="ingresos_excel"),
    path("informe/", paginas.informe, name="informe"),
    path("informe/<str:tipo>/", paginas.informe_archivo, name="informe_archivo"),
    path("campanas/", paginas.campanas, name="campanas"),
    path("campanas/significados/", paginas.significados, name="significados"),
    path("empresas/", paginas.empresas, name="empresas"),
    path("empresas/tarifas/", paginas.tarifas, name="tarifas"),
    path("historial/", paginas.historial, name="historial"),
]
