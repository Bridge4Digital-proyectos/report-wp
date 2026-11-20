from django.contrib import admin
from django.contrib.auth import views as auth
from django.urls import include, path

admin.site.site_header = "Reportes de difusiones"
admin.site.site_title = "Reportes de difusiones"

urlpatterns = [
    path("ingresar/", auth.LoginView.as_view(template_name="registro/ingresar.html"), name="login"),
    path("salir/", auth.LogoutView.as_view(), name="logout"),
    path("admin/", admin.site.urls),
    path("connectly/", include("connectly.urls")),
    path("generador/", include("generador.urls")),
    path("", include("nucleo.urls")),
]
