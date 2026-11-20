"""Cómo se nombra la plataforma en todo lo que recibe la empresa (reporte HTML, Excel y PDF).

La empresa nunca ve "Connectly": se muestra como "Cocco". La app interna sí usa el nombre real.
"""
import re

PLATAFORMA_CLIENTE = "Cocco"
_CONNECTLY = re.compile("connectly", re.IGNORECASE)


def para_cliente(valor):
    """Reemplaza "Connectly" por "Cocco" en un texto (otros valores pasan sin cambios)."""
    return _CONNECTLY.sub(PLATAFORMA_CLIENTE, valor) if isinstance(valor, str) else valor


def libro_para_cliente(libro):
    """Aplica para_cliente a todas las celdas de texto y a los nombres de hoja de un libro de openpyxl."""
    for hoja in libro.worksheets:
        hoja.title = para_cliente(hoja.title)
        for fila in hoja.iter_rows():
            for celda in fila:
                if isinstance(celda.value, str) and _CONNECTLY.search(celda.value):
                    celda.value = para_cliente(celda.value)
    return libro
