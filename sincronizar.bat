@echo off
rem Trae ahora los reportes de Connectly (lo mismo que hace la app cada dia a la hora configurada).
cd /d "%~dp0"
docker compose exec web python manage.py sincronizar_connectly %*
pause
