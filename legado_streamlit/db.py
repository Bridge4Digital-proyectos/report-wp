"""Base SQLite local: empresas, campañas, mensajes e historial de cargas."""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

RUTA_DB = Path(__file__).parent.parent / "data" / "reportes.db"  # la app anterior quedó en legado_streamlit/
# Categorías de Meta, siempre en mayúsculas en toda la app.
CATEGORIAS = ["UTILITY", "MARKETING"]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS empresas (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS campanas (
    id INTEGER PRIMARY KEY,
    plataforma TEXT NOT NULL,
    nombre TEXT NOT NULL,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    categoria TEXT NOT NULL DEFAULT 'UTILITY',
    solicitado_por TEXT,
    fecha_solicitud TEXT,
    UNIQUE (plataforma, nombre, empresa_id)
);
CREATE TABLE IF NOT EXISTS mensajes (
    id INTEGER PRIMARY KEY,
    campana_id INTEGER NOT NULL REFERENCES campanas(id),
    telefono TEXT,
    session_id TEXT NOT NULL,
    despachado_en TEXT, enviado_en TEXT, entregado_en TEXT, leido_en TEXT, opt_out_en TEXT,
    error_code TEXT, error_msg TEXT,
    estado TEXT NOT NULL,
    respuesta TEXT,
    clics_boton INTEGER DEFAULT 0,
    clics_link INTEGER DEFAULT 0,
    plantilla TEXT,
    UNIQUE (campana_id, session_id)
);
CREATE TABLE IF NOT EXISTS cargas (
    id INTEGER PRIMARY KEY,
    archivo TEXT, plataforma TEXT,
    empresa_id INTEGER REFERENCES empresas(id),
    fecha_carga TEXT,
    filas_nuevas INTEGER, filas_duplicadas INTEGER
);
CREATE TABLE IF NOT EXISTS significados (
    id INTEGER PRIMARY KEY,
    empresa_id INTEGER NOT NULL REFERENCES empresas(id),
    difusion TEXT NOT NULL,          -- nombre de la campaña normalizado (ver normalizar)
    valor TEXT NOT NULL,             -- "Calificación 4", "Opción 1", "Internet lento", "Dice que ya pagó"...
    significado TEXT, sentido TEXT,
    UNIQUE (empresa_id, difusion, valor)
);
"""

COLUMNAS_MENSAJE = [
    "telefono", "session_id", "despachado_en", "enviado_en", "entregado_en", "leido_en",
    "opt_out_en", "error_code", "error_msg", "estado", "respuesta", "clics_boton",
    "clics_link", "plantilla",
]


def conectar(ruta=None) -> sqlite3.Connection:
    ruta = Path(ruta or RUTA_DB)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(ESQUEMA)
    columnas = {f[1] for f in con.execute("PRAGMA table_info(cargas)")}
    if "filas_actualizadas" not in columnas:
        con.execute("ALTER TABLE cargas ADD COLUMN filas_actualizadas INTEGER DEFAULT 0")
        con.commit()
    if con.execute("SELECT 1 FROM campanas WHERE categoria <> UPPER(categoria) LIMIT 1").fetchone():
        con.execute("UPDATE campanas SET categoria = UPPER(categoria)")
        con.commit()
    return con


def empresas(con) -> list[tuple[int, str]]:
    return con.execute("SELECT id, nombre FROM empresas ORDER BY nombre").fetchall()


def crear_empresa(con, nombre: str) -> int:
    nombre = nombre.strip()
    con.execute("INSERT OR IGNORE INTO empresas (nombre) VALUES (?)", (nombre,))
    con.commit()
    return con.execute("SELECT id FROM empresas WHERE nombre = ?", (nombre,)).fetchone()[0]


def buscar_campana(con, plataforma, nombre, empresa_id) -> dict | None:
    fila = con.execute(
        "SELECT id, categoria, solicitado_por, fecha_solicitud FROM campanas "
        "WHERE plataforma = ? AND nombre = ? AND empresa_id = ?",
        (plataforma, nombre, empresa_id),
    ).fetchone()
    if not fila:
        return None
    return dict(zip(["id", "categoria", "solicitado_por", "fecha_solicitud"], fila))


def solicitantes(con) -> list[str]:
    filas = con.execute(
        "SELECT DISTINCT solicitado_por FROM campanas WHERE solicitado_por <> '' ORDER BY 1"
    ).fetchall()
    return [f[0] for f in filas]


# Campos que un reporte más reciente puede completar; los vacíos nunca borran lo que ya había.
CAMPOS_MEZCLA = ["telefono", "despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en",
                 "error_code", "error_msg", "respuesta", "plantilla"]
DELTAS = {"entregados": "entregado_en", "leidos": "leido_en", "respuestas": "respuesta", "opt_outs": "opt_out_en"}


def _vacio(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or v == ""


def _normal(v):
    if _vacio(v):
        return None
    return str(int(v)) if isinstance(v, (int, float)) else str(v)


def _claves(df: pd.DataFrame) -> pd.Series:
    """Clave de cada mensaje: id de sesión, o teléfono + despacho si no lo hay."""
    tiene_id = df["session_id"].notna() & (df["session_id"] != "")
    return df["session_id"].where(tiene_id, df["telefono"].astype(str) + "|" + df["despachado_en"].astype(str))


def _mezclar(nueva: dict, vieja: dict) -> dict:
    """Fila resultante: el dato nuevo si viene, si no el anterior."""
    from importers import calcular_estado

    m = {c: vieja.get(c) if _vacio(nueva.get(c)) else nueva.get(c) for c in CAMPOS_MEZCLA}
    m = {c: None if _vacio(v) else v for c, v in m.items()}
    m["respuesta"] = m["respuesta"] or ""
    for c in ["clics_boton", "clics_link"]:
        m[c] = max(int(nueva.get(c) or 0), int(vieja.get(c) or 0))
    m["estado"] = calcular_estado(m["entregado_en"], m["leido_en"], m["enviado_en"], m["error_code"])
    return m


def _plan_carga(con, df, plataforma, empresa_id):
    """Para cada fila del archivo: (campaña, clave, tipo, fila_mezclada, fila_anterior).

    tipo es 'nueva', 'actualizada' o 'sin_cambios'. No escribe nada en la base.
    """
    df = df.assign(session_id=_claves(df))
    columnas = ", ".join(c for c in COLUMNAS_MENSAJE)
    plan = []
    for nombre, grupo in df.groupby("campana", sort=False):
        previa = buscar_campana(con, plataforma, nombre, empresa_id) if empresa_id else None
        existentes = {}
        if previa:
            viejos = pd.read_sql_query(f"SELECT {columnas} FROM mensajes WHERE campana_id = ?",
                                       con, params=(previa["id"],))
            existentes = {r["session_id"]: r for r in viejos.to_dict("records")}
        for fila in grupo.to_dict("records"):
            vieja = existentes.get(fila["session_id"])
            mezcla = _mezclar(fila, vieja or {})
            if vieja is None:
                tipo = "nueva"
            elif any(_normal(mezcla[c]) != _normal(vieja.get(c)) for c in mezcla):
                tipo = "actualizada"
            else:
                tipo = "sin_cambios"
            plan.append((nombre, fila["session_id"], tipo, mezcla, vieja or {}))
    return plan


def comparar_carga(con, df: pd.DataFrame, plataforma: str, empresa_id) -> pd.DataFrame:
    """Qué aportaría el archivo frente a lo ya guardado, por campaña. Solo lectura."""
    filas = []
    for nombre, _, tipo, mezcla, vieja in _plan_carga(con, df, plataforma, empresa_id):
        f = {"campana": nombre, "mensajes": 1, "nuevas": int(tipo == "nueva"),
             "actualizadas": int(tipo == "actualizada"), "sin_cambios": int(tipo == "sin_cambios")}
        for nombre_delta, col in DELTAS.items():
            f[nombre_delta] = int(not _vacio(mezcla[col])) - int(not _vacio(vieja.get(col)))
        f["fallidos_antes"] = int(vieja.get("estado") == "Fallido")
        f["fallidos_despues"] = int(mezcla["estado"] == "Fallido")
        filas.append(f)
    if not filas:
        return pd.DataFrame()
    return pd.DataFrame(filas).groupby("campana", sort=False).sum().reset_index()


def ultima_carga(con, archivo: str, empresa_id) -> str | None:
    fila = con.execute("SELECT MAX(fecha_carga) FROM cargas WHERE archivo = ? AND empresa_id = ?",
                       (archivo, empresa_id)).fetchone()
    return fila[0] if fila else None


def guardar_carga(con, df: pd.DataFrame, plataforma: str, empresa_id: int,
                  archivo: str, datos_campanas: dict) -> tuple[int, int, int]:
    """Guarda el reporte quedándose con lo más nuevo. Devuelve (nuevas, actualizadas, sin_cambios).

    Los mensajes que ya estaban se actualizan con lo que traiga el archivo (más lecturas,
    respuestas, etc.); un campo vacío en el archivo nunca borra el valor guardado.
    datos_campanas: {nombre_campana: {categoria, solicitado_por, fecha_solicitud}}
    """
    with con:
        for nombre in df["campana"].unique():
            datos = datos_campanas.get(nombre, {})
            con.execute(
                "INSERT INTO campanas (plataforma, nombre, empresa_id, categoria, solicitado_por, fecha_solicitud) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (plataforma, nombre, empresa_id) DO UPDATE SET "
                "categoria = excluded.categoria, solicitado_por = excluded.solicitado_por, "
                "fecha_solicitud = excluded.fecha_solicitud",
                (plataforma, nombre, empresa_id, (datos.get("categoria") or "UTILITY").upper(),
                 datos.get("solicitado_por"), datos.get("fecha_solicitud")),
            )
        plan = _plan_carga(con, df, plataforma, empresa_id)
        ids = {n: buscar_campana(con, plataforma, n, empresa_id)["id"] for n in df["campana"].unique()}
        cols = [c for c in COLUMNAS_MENSAJE if c != "session_id"]
        for nombre, clave, tipo, mezcla, _ in plan:
            valores = [_valor(mezcla[c]) for c in cols]
            if tipo == "nueva":
                con.execute(
                    f"INSERT OR IGNORE INTO mensajes (campana_id, session_id, {', '.join(cols)}) "
                    f"VALUES (?, ?, {', '.join('?' * len(cols))})",
                    (ids[nombre], clave, *valores))
            elif tipo == "actualizada":
                con.execute(
                    f"UPDATE mensajes SET {', '.join(c + ' = ?' for c in cols)} "
                    "WHERE campana_id = ? AND session_id = ?",
                    (*valores, ids[nombre], clave))
        cuenta = {t: sum(1 for p in plan if p[2] == t) for t in ["nueva", "actualizada", "sin_cambios"]}
        con.execute(
            "INSERT INTO cargas (archivo, plataforma, empresa_id, fecha_carga, filas_nuevas, "
            "filas_actualizadas, filas_duplicadas) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (archivo, plataforma, empresa_id, datetime.now().isoformat(timespec="seconds"),
             cuenta["nueva"], cuenta["actualizada"], cuenta["sin_cambios"]),
        )
    return cuenta["nueva"], cuenta["actualizada"], cuenta["sin_cambios"]


def _valor(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def campanas(con) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT c.id, e.nombre AS empresa, c.plataforma, c.nombre AS campana, c.categoria, "
        "c.solicitado_por, c.fecha_solicitud, COUNT(m.id) AS mensajes, MIN(m.despachado_en) AS primer_envio "
        "FROM campanas c JOIN empresas e ON e.id = c.empresa_id "
        "LEFT JOIN mensajes m ON m.campana_id = c.id "
        "GROUP BY c.id ORDER BY primer_envio DESC",
        con,
    )


def actualizar_campana(con, campana_id, categoria, solicitado_por, fecha_solicitud):
    with con:
        con.execute(
            "UPDATE campanas SET categoria = ?, solicitado_por = ?, fecha_solicitud = ? WHERE id = ?",
            ((categoria or "UTILITY").upper(), solicitado_por, fecha_solicitud, campana_id),
        )


def mensajes(con) -> pd.DataFrame:
    """Todos los mensajes con los datos de su campaña y empresa; los filtros se aplican en pandas."""
    df = pd.read_sql_query(
        "SELECT e.nombre AS empresa, c.plataforma, c.nombre AS campana, c.categoria, "
        "c.solicitado_por, c.fecha_solicitud, m.* "
        "FROM mensajes m JOIN campanas c ON c.id = m.campana_id JOIN empresas e ON e.id = c.empresa_id",
        con,
    )
    for col in ["despachado_en", "enviado_en", "entregado_en", "leido_en", "opt_out_en"]:
        # ISO8601: Connectly trae microsegundos y S1 no; sin esto, las fechas del otro formato quedan vacías.
        df[col] = pd.to_datetime(df[col], errors="coerce", format="ISO8601")
    df["fecha_solicitud"] = pd.to_datetime(df["fecha_solicitud"], errors="coerce").dt.date
    df["respuesta"] = df["respuesta"].fillna("")
    return df


def historial_cargas(con) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT g.fecha_carga AS 'Fecha de carga', e.nombre AS Empresa, g.plataforma AS Plataforma, "
        "g.archivo AS Archivo, g.filas_nuevas AS Nuevos, COALESCE(g.filas_actualizadas, 0) AS Actualizados, "
        "g.filas_duplicadas AS 'Sin cambios' "
        "FROM cargas g JOIN empresas e ON e.id = g.empresa_id ORDER BY g.id DESC",
        con,
    )


def borrar_todo(con, carpeta_respaldo=None) -> Path:
    """Guarda un respaldo de la base y borra empresas, campañas, mensajes e historial de cargas."""
    carpeta = Path(carpeta_respaldo or RUTA_DB.parent / "respaldos")
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"reportes_{datetime.now():%Y%m%d_%H%M%S}.db"
    with sqlite3.connect(destino) as copia:
        con.backup(copia)
    copia.close()
    with con:
        for tabla in ["significados", "mensajes", "cargas", "campanas", "empresas"]:
            con.execute(f"DELETE FROM {tabla}")
    con.execute("VACUUM")
    return destino


def normalizar(nombre: str) -> str:
    """Clave de campaña: sin mayúsculas ni espacios repetidos (igual que al agrupar campañas)."""
    return " ".join(str(nombre).casefold().split())


def resumen_empresas(con) -> pd.DataFrame:
    return pd.read_sql_query(
        "SELECT e.id, e.nombre, COUNT(DISTINCT c.id) AS envios, COUNT(m.id) AS mensajes, "
        "MAX(m.despachado_en) AS ultimo_envio "
        "FROM empresas e LEFT JOIN campanas c ON c.empresa_id = e.id LEFT JOIN mensajes m ON m.campana_id = c.id "
        "GROUP BY e.id ORDER BY e.nombre",
        con,
    )


def renombrar_empresa(con, empresa_id: int, nombre: str):
    """Cambia el nombre; falla con ValueError si queda vacío o ya lo usa otra empresa."""
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        raise ValueError("El nombre no puede quedar vacío.")
    otra = con.execute("SELECT id FROM empresas WHERE lower(nombre) = lower(?) AND id <> ?",
                       (nombre, empresa_id)).fetchone()
    if otra:
        raise ValueError(f"Ya existe otra empresa llamada «{nombre}».")
    with con:
        con.execute("UPDATE empresas SET nombre = ? WHERE id = ?", (nombre, empresa_id))


def significados(con) -> dict:
    """{(nombre de empresa, campaña normalizada): {valor: (significado, sentido)}}."""
    salida: dict = {}
    for empresa, difusion, valor, significado, sentido in con.execute(
            "SELECT e.nombre, s.difusion, s.valor, s.significado, s.sentido "
            "FROM significados s JOIN empresas e ON e.id = s.empresa_id"):
        salida.setdefault((empresa, difusion), {})[valor] = (significado, sentido)
    return salida


def _empresa_id(con, empresa: str) -> int:
    return con.execute("SELECT id FROM empresas WHERE nombre = ?", (empresa,)).fetchone()[0]


def guardar_significados(con, empresa: str, difusion: str, filas):
    """filas: [(valor, significado, sentido)] para una campaña."""
    eid, clave = _empresa_id(con, empresa), normalizar(difusion)
    with con:
        con.executemany(
            "INSERT INTO significados (empresa_id, difusion, valor, significado, sentido) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT (empresa_id, difusion, valor) DO UPDATE SET significado = excluded.significado, "
            "sentido = excluded.sentido",
            [(eid, clave, v, (sig or "").strip() or v, sen) for v, sig, sen in filas])


def borrar_significados(con, empresa: str, difusion: str):
    with con:
        con.execute("DELETE FROM significados WHERE empresa_id = ? AND difusion = ?",
                    (_empresa_id(con, empresa), normalizar(difusion)))
