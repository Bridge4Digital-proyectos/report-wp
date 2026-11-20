@echo off
rem Crea un usuario administrador para ingresar a la app.
cd /d "%~dp0"
docker compose exec web python manage.py createsuperuser
pause
