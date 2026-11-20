#!/bin/sh
# Espera la base de datos y aplica migraciones antes de arrancar (solo el servicio web las aplica).
set -e
if [ "${MIGRAR:-0}" = "1" ]; then
  for i in $(seq 1 30); do
    python manage.py migrate --noinput && break
    echo "Esperando la base de datos ($i)..."; sleep 2
  done
fi
exec "$@"
