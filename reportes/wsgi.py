import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "reportes.settings")
application = get_wsgi_application()

# Precarga los mensajes al arrancar y cada vez que cambian (solo en el servidor web, no en comandos ni pruebas).
from nucleo.servicios.datos import mantener_caliente  # noqa: E402

mantener_caliente()
