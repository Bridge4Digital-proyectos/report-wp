"""Configuración del proyecto. Todo lo sensible o propio de cada equipo viene de variables de entorno (.env)."""
import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _cargar_env(ruta: Path):
    """Lee un .env simple (CLAVE=valor) sin dependencias extra; las variables ya definidas tienen prioridad."""
    if not ruta.exists():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if linea and not linea.startswith("#") and "=" in linea:
            clave, valor = linea.split("=", 1)
            os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


_cargar_env(BASE_DIR / ".env")


def _lista(nombre, defecto=""):
    return [x.strip() for x in os.environ.get(nombre, defecto).split(",") if x.strip()]


DEBUG = os.environ.get("DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("SECRET_KEY") or ("solo-para-desarrollo-local" if DEBUG else None)
if not SECRET_KEY:
    raise RuntimeError("Falta SECRET_KEY en el archivo .env (ver .env.ejemplo).")
ALLOWED_HOSTS = _lista("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = _lista("CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "nucleo",
    "connectly",
    "generador",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.auth.middleware.LoginRequiredMiddleware",  # todo pide login salvo la página de ingreso
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "reportes.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "nucleo.contexto.navegacion",
    ]},
}]
WSGI_APPLICATION = "reportes.wsgi.application"


def _base_de_datos():
    url = os.environ.get("DATABASE_URL")
    if not url:  # desarrollo y pruebas
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "data" / "django.sqlite3"}
    u = urlparse(url)
    return {"ENGINE": "django.db.backends.postgresql", "NAME": u.path.lstrip("/"), "USER": u.username,
            "PASSWORD": u.password, "HOST": u.hostname, "PORT": u.port or 5432, "CONN_MAX_AGE": 60}


DATABASES = {"default": _base_de_datos()}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "es"
TIME_ZONE = os.environ.get("TIME_ZONE", "America/La_Paz")
USE_I18N = True
# Las fechas se guardan tal como vienen en los reportes (sin zona horaria), igual que en la app anterior.
USE_TZ = False

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Subidas grandes (reportes de 100 000+ filas).
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 50 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 20000

CARPETA_RESPALDOS = Path(os.environ.get("CARPETA_RESPALDOS", BASE_DIR / "respaldos"))
SINCRONIZAR_HORA = os.environ.get("SINCRONIZAR_HORA", "07:00")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"consola": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["consola"], "level": "INFO"},
}
