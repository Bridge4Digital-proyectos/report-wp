@echo off
rem Copia los datos de la app anterior (data\reportes.db) a la app nueva. Solo hace falta una vez.
cd /d "%~dp0"
docker compose exec web python manage.py importar_base_anterior data/reportes.db
pause
