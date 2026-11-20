def navegacion(request):
    """Menú principal. Cada ítem: url, texto y las vistas en las que se marca como activo."""
    return {"menu": [
        {"url": "dashboard", "texto": "Dashboard", "activos": {"dashboard"}},
        {"url": "connectly:inicio", "texto": "Connectly", "activos": {"connectly:inicio", "connectly:cargar"}},
        {"url": "campanas", "texto": "Campañas", "activos": {"campanas", "significados"}},
        {"url": "empresas", "texto": "Empresas", "activos": {"empresas", "tarifas"}},
        {"url": "informe", "texto": "Reportes", "activos": {"informe", "generador:inicio"}},
        {"url": "historial", "texto": "Historial", "activos": {"historial"}},
    ]}
