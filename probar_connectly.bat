@echo off
rem Solo lectura: muestra que reportes devuelve la API de Connectly, sin guardar nada.
cd /d "%~dp0"
docker compose exec web python manage.py sincronizar_connectly --probar
pause
