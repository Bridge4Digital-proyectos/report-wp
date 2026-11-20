# Reportes de difusiones (Django)

App web para ver los reportes de difusiones de WhatsApp por empresa. Los reportes de **Connectly** se traen solos todos los días por la API.

- **Apps:** `nucleo` (empresas, campañas, mensajes, indicadores e informes), `connectly` (API, sincronización y CSV manual) y `generador` (reporte HTML).
- **Funcionamiento:** corre en este equipo con Docker. Hay tres servicios:
  - `web`: la app, en http://localhost:8010;
  - `db`: la base de datos PostgreSQL;
  - `programador`: sincroniza Connectly una vez al día.

## Primera vez

1. **Abre Docker Desktop.** En *Settings → General*, activa **"Start Docker Desktop when you sign in"**. Así, la app y la sincronización diaria arrancan solas al prender la PC.
2. **Ejecuta `iniciar.bat`.** La primera vez crea el archivo `.env` con claves nuevas, construye la app (tarda unos minutos) y abre el navegador.
3. **Ejecuta `crear_usuario.bat`** y crea tu usuario administrador. Después ingresa en http://localhost:8010.
4. **Ejecuta `importar_datos_anteriores.bat`** para traer los datos de la app anterior desde `data/reportes.db`. Al final muestra los totales por empresa para comparar.

## Conectar Connectly (API)

1. **Consigue en Connectly el *Business ID* y una *API key*.**
   - Están en la configuración del negocio, en la sección API o desarrolladores.
   - El Business ID también suele verse en la dirección del navegador cuando estás dentro del negocio.
   - Si no aparecen, pídeselos al soporte de Connectly.
   - La app usa el reporte programado **"Campaign_Report_-_Ultimos_30_dias_diario"**, que Connectly genera cada día con todas las campañas de los últimos 30 días. La API no permite generarlo en el momento.
2. **Abre el archivo `.env` con el Bloc de notas** y pega la clave en `CONNECTLY_API_KEY_TIGO=...`.
   - Para otra empresa, agrega otra línea, por ejemplo `CONNECTLY_API_KEY_VIVA=...`.
   - **No compartas este archivo ni pegues la clave en chats ni correos.**
3. **Ejecuta `iniciar.bat`** para que la app lea la clave nueva.
4. **Registra la cuenta.** En la app, ve a **Admin → Cuentas de Connectly → Agregar** y completa:
   - la empresa;
   - el Business ID;
   - el nombre de la variable (por ejemplo `CONNECTLY_API_KEY_TIGO`);
   - el nombre del reporte (`Campaign_Report_-_Ultimos_30_dias_diario`) y su tipo (`campaign.sessions.v1`), que ya vienen puestos por defecto.
5. **Ejecuta `probar_connectly.bat`.** Solo lee: muestra qué reportes devuelve la API y qué columnas trae el CSV, sin guardar nada.
6. **Sincroniza.** Si la prueba sale bien, ve a **Connectly → Sincronizar ahora** o ejecuta `sincronizar.bat`. Desde ahí, el programador lo hace solo cada día a la hora `SINCRONIZAR_HORA` del `.env` (07:00 por defecto).

**Cómo funciona la sincronización:**
- Cada día se importa el reporte de los últimos 30 días completo, con todas las campañas, y cada reporte una sola vez. Tarda 1 o 2 minutos.
- Una campaña de más de 30 días queda guardada aunque ya no aparezca en el reporte.
- Los mensajes que ya estaban se actualizan con los datos nuevos (lecturas, respuestas), y un dato vacío nunca borra lo guardado.
- Las campañas nuevas quedan como UTILITY. Corrígelas en **Campañas** si son MARKETING.
- El resultado de cada sincronización queda en **Connectly → Registro de sincronizaciones**.

## Indicadores del Dashboard

El Dashboard (toda la empresa, o una campaña al elegirla) muestra:
- **Efectividad de gestión:** mensajes **enviados** sobre los mensajes de la base. Las respuestas de los clientes se miden aparte, en la **tasa de respuesta**.
- **Tasas:** entrega y lectura.
- **Clics (CTR):** en botones y enlaces.
- **Tiempos:** lectura en la primera hora y tiempo hasta la lectura.
- **Horario de entrega** y **mapa de calor de lectura**, en hora local.
- **Calidad de la base:** números sin WhatsApp, bloqueos de Meta, bajas de marketing y números repetidos. Los repetidos se pueden descargar en Excel.
- **Satisfacción:** CSAT y sentimiento neto. Solo en campañas con encuesta o calificación.
- **Ingresos de Bridge4** (el Dashboard es de uso interno): mensajes entregados × precio que cobramos a la empresa por categoría.
  Se ven en total, por categoría, por mes y por campaña, y se descargan en Excel.
  Los precios se cargan en **Empresas → Tarifas**.

## Reportes (Informe y Reporte HTML)

En **Reportes**, la pestaña **Informe** arma el Excel o PDF y la pestaña **Reporte HTML** arma el reporte para compartir. Elige una campaña guardada o sube un CSV de Connectly. Después pulsa **Ver reporte** o **Descargar HTML**. El archivo:
- lleva la marca Bridge4 Digital;
- funciona sin conexión y se puede enviar por correo o imprimir como PDF desde el navegador.

Trae estas secciones:
- **Resumen:** contactos, enviados, entregados, leídos, fallidos y rechazados.
- **Indicadores clave**, **horarios** (entrega y mapa de calor de lectura) y **calidad de la base**, con la descarga de los números repetidos.
- **Efectividad de gestión:** mensajes enviados sobre la base, y **tasa de respuesta** aparte.
- **Lo que recibe la empresa** (reporte HTML, Excel y PDF) **no muestra costos**, y la plataforma aparece como **Cocco**, nunca "Connectly".
  Los ingresos solo se ven en el Dashboard interno.
- **Rechazadas:** mensajes que WhatsApp/Meta no aceptó y sus motivos. Los fallidos van aparte.
- **Respuesta del cliente:** tipo, sentido, opciones elegidas y calificación.
- **Detalle por línea:** con buscador, filtros y descarga en CSV.

## Uso diario

| Archivo | Para qué |
|---|---|
| `iniciar.bat` | Inicia la app y abre el navegador |
| `detener.bat` | Detiene la app; los datos quedan guardados |
| `sincronizar.bat` | Trae ahora los reportes de Connectly |
| `probar_connectly.bat` | Prueba la API sin guardar nada |
| `respaldar.bat` | Respaldo completo en la carpeta `respaldos/` |
| `crear_usuario.bat` | Crea otro usuario administrador |

Los usuarios que no son administradores se crean en **Admin → Usuarios**.

## Usarla desde otra PC de la red (opcional)

En `.env`:
1. Cambia `PUERTO=8010`.
2. Agrega la IP de este equipo en `ALLOWED_HOSTS`, por ejemplo `localhost,127.0.0.1,192.168.1.50`.
3. Agrégala también en `CSRF_TRUSTED_ORIGINS`, por ejemplo `http://192.168.1.50:8010`.

Después ejecuta `iniciar.bat`.

## Desarrollo

```
.venv\Scripts\python.exe -m pip install -r requirements.txt
set DEBUG=1
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py test
.venv\Scripts\python.exe manage.py runserver
```

Sin `DATABASE_URL`, la app usa SQLite en `data/django.sqlite3`. La app anterior (Streamlit) quedó en `legado_streamlit/`, por si hace falta compararla.
