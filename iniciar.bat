@echo off
rem Inicia la app de reportes (Docker) y la abre en el navegador.
setlocal
cd /d "%~dp0"
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop no esta abierto. Abrelo, espera a que diga "Engine running" y vuelve a ejecutar este archivo.
  pause
  exit /b 1
)
if not exist ".env" (
  powershell -NoProfile -Command "$r=[Security.Cryptography.RandomNumberGenerator]::Create(); function Clave($n){$b=New-Object byte[] $n; $r.GetBytes($b); ($b | ForEach-Object { $_.ToString('x2') }) -join ''}; $c=Get-Content '.env.ejemplo' -Raw; $c=$c -replace 'SECRET_KEY=.*', ('SECRET_KEY=' + (Clave 40)); $c=$c -replace 'POSTGRES_PASSWORD=.*', ('POSTGRES_PASSWORD=' + (Clave 20)); [IO.File]::WriteAllText((Join-Path (Get-Location) '.env'), $c)"
  echo Se creo el archivo .env con claves nuevas. Agrega ahi la API key de Connectly cuando la tengas.
)
echo Iniciando la app (la primera vez tarda unos minutos)...
docker compose up -d --build
if errorlevel 1 (
  pause
  exit /b 1
)
timeout /t 5 >nul
start "" http://localhost:8010
