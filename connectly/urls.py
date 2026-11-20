from django.urls import path

from connectly import views

app_name = "connectly"
urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("sincronizar/", views.sincronizar_ahora, name="sincronizar"),
    path("cargar/", views.cargar, name="cargar"),
]
