@echo off
rem Guarda un respaldo completo de los datos en la carpeta "respaldos".
cd /d "%~dp0"
docker compose exec web python manage.py respaldar
pause
