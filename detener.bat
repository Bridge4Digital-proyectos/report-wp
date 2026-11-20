@echo off
rem Detiene la app (los datos quedan guardados en Docker).
cd /d "%~dp0"
docker compose stop
pause
