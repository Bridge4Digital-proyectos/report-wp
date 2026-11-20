FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BROWSER_PATH=/usr/bin/chromium

# Chromium: lo usa kaleido para dibujar los gráficos del PDF y del Excel.
RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium fonts-dejavu-core tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY manage.py ./
COPY reportes ./reportes
COPY nucleo ./nucleo
COPY connectly ./connectly
COPY generador ./generador
COPY templates ./templates
COPY docker/entrada.sh /entrada.sh

RUN chmod +x /entrada.sh \
    && SECRET_KEY=solo-para-build python manage.py collectstatic --noinput \
    && useradd --create-home app && mkdir -p /app/data /app/respaldos && chown -R app /app
USER app

EXPOSE 8000
ENTRYPOINT ["/entrada.sh"]
# Un proceso con varios hilos: los datos (cientos de miles de mensajes) se cargan una sola vez en memoria.
CMD ["gunicorn", "reportes.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--worker-class", "gthread", "--timeout", "300"]
