from django.urls import path

from generador import views

app_name = "generador"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("reporte/", views.reporte, name="reporte"),
    path("quitar-archivo/", views.quitar_archivo, name="quitar_archivo"),
]
