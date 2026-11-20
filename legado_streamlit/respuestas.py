"""Convierte la respuesta cruda de cada cliente (JSON de encuesta, 'clave: valor' o texto libre)
en datos legibles: tipo de respuesta, calificación 1–5, motivos mencionados y comentario."""
import json
import re
import unicodedata

import pandas as pd

ENCUESTA = "Encuesta respondida"
# Sentido de una respuesta o de un motivo. Cada campaña puede redefinirlo (tabla `significados`).
POSITIVA, NEGATIVA, NEUTRAL = "Positiva", "Negativa", "Neutral"
SENTIDOS = [POSITIVA, NEUTRAL, NEGATIVA]
PROBLEMA, POSITIVO = NEGATIVA, POSITIVA  # nombres usados en la detección de motivos

# Claves de las encuestas en formato texto "calificacion: 2, problemas: mala_cobertura".
_CLAVES = ["calificacion", "satisfaccion", "rating", "problemas_otros", "aspectos_otros", "otro_motivo",
           "problemas", "aspectos_positivos", "aspectos_neutrales", "aspectos", "razones", "sentimiento", "label_2"]
_KV = re.compile(r"(?:^|,\s*)(" + "|".join(_CLAVES) + r"):\s*")
_TOKEN = re.compile(r"^[\wñ]+$")

# Texto libre: (categoría, patrón) en orden de prioridad, sobre el texto sin tildes y en minúsculas.
_LIBRE = [
    ("Abrió un caso en S1", re.compile(r"^abrio caso n")),  # S1 no trae el texto: solo el número de caso
    ("Sticker, emoji o multimedia", re.compile(r"currently unsupported|type: (sticker|image|audio|video|document)|^[\W_]+$")),
    ("Respuesta automática", re.compile(r"gracias por (tu|su|comunicarte|escribir)|como podemos ayudarte|"
                                        r"en que (te )?puedo ayudar|en este momento no podemos|horario de atencion|"
                                        r"mensaje automatico|bienvenid|pago exitoso|soy .{0,30}asesor|te saluda")),
    ("Dice que ya pagó", re.compile(r"\bya (pague|pago|cancele|deposite)|\bpagad[oa]\b|\bpague\b|comprobante|\bqr\b")),
    ("No quiere mensajes / número equivocado", re.compile(
        r"equivocad|dar de baja|no quiero|no me (interesa|estresen|molesten)|^no( gracias)?\W*$|molest|corten|"
        r"callate|estaf|por que me mandan|imbecil|mierda|carajo|ladron|ratero")),
    ("Consulta sobre el pago", re.compile(r"pagar|pagando|cuanto (debo|es|sale)|deuda|factura|monto|\bpago\b|cancelar")),
    ("Queja del servicio", re.compile(r"senal|lent|internet|se corta|cortes?\b|caro|pesim|horrible|malisim|\bmal[oa]?\b|"
                                      r"no (hay|funciona|navega|carga|da)\b|reclam|wifi|basura|megas|cobrando")),
    ("Saludo", re.compile(r"^(hola|buen[oa]?s?|buen dia|saludos)\b")),
    ("Agradecimiento / OK", re.compile(r"gracias|^(ok\w*|vale|listo|esta bien|bien|si|ya|de acuerdo|perfecto|entendido)\W*$")),
]
OTRO = "Otro mensaje"
TIPOS = [ENCUESTA] + [c for c, _ in _LIBRE] + [OTRO]
# Sentido sugerido para el texto libre (el resto, Neutral).
SENTIDO_TIPO = {"Dice que ya pagó": POSITIVA, "Agradecimiento / OK": POSITIVA,
                "Queja del servicio": NEGATIVA, "No quiere mensajes / número equivocado": NEGATIVA}


def valor_nota(n: int) -> str:
    return f"Calificación {int(n)}"


def sentido_nota(n: int) -> str:
    return POSITIVA if n >= 4 else NEGATIVA if n <= 2 else NEUTRAL


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def etiqueta(token: str) -> str:
    """'mala_cobertura_o_señal' -> 'Mala cobertura o señal'; 'otros' -> 'Otro motivo'."""
    t = str(token).strip().replace("_", " ").replace("senial", "señal")
    if t.lower() in ("otros", "otro"):
        return "Otro motivo"
    return t[:1].upper() + t[1:]


_POSITIVAS = re.compile(r"^(buen|excelente|fluid|rapid|estable|sin cortes|video fluido|videos y transmision)")
_NEGATIVAS = re.compile(r"(^mal|lent|se corta|cortes?\b|no (navega|puede|carga|hay|funciona)|tarda|se detiene|"
                        r"detienen|caid|inestable|intermit|sin senal|pesim|caro|congel)")


def grupo_de(nombre: str, origen: str) -> str:
    """Grupo por el significado del motivo; si no se reconoce, el de la pregunta de donde viene."""
    base = _sin_tildes(nombre.casefold())
    if base.startswith(("otro motivo", "opcion")):
        return NEUTRAL
    if _POSITIVAS.search(base):
        return POSITIVO
    if _NEGATIVAS.search(base):
        return PROBLEMA
    return origen


def _lista(v) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    partes = [p.strip() for p in str(v or "").split(",")]
    return [p for p in partes if p and _TOKEN.match(p)]


def _leer_kv(texto: str) -> dict | None:
    marcas = list(_KV.finditer(texto))
    if not marcas or marcas[0].start() != 0:
        return None
    datos = {}
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        datos[m.group(1)] = texto[m.end():fin].strip()
    return datos


def _datos_encuesta(texto: str) -> dict | None:
    """Busca, entre los tramos separados por ' | ', el que sea una encuesta."""
    for parte in reversed([p.strip() for p in texto.split(" | ")]):
        if parte.startswith("{"):
            try:
                d = json.loads(parte)
                if isinstance(d, dict) and set(d) & set(_CLAVES):
                    return d
            except ValueError:
                pass
        d = _leer_kv(parte)
        if d:
            return d
    return None


def _nota(d: dict):
    for clave in ("satisfaccion", "calificacion", "rating"):
        v = d.get(clave)
        try:
            n = int(str(v).strip())
            if 1 <= n <= 5:
                return n
        except (TypeError, ValueError):
            pass
    return pd.NA


def interpretar(texto: str) -> dict:
    """Una respuesta -> {tipo, calificacion, motivos: [(etiqueta, grupo)], comentario}."""
    texto = str(texto or "").strip()
    d = _datos_encuesta(texto)
    if d is None:
        base = _sin_tildes(texto.casefold())
        tipo = next((c for c, patron in _LIBRE if patron.search(base)), OTRO)
        return {"tipo": tipo, "calificacion": pd.NA, "motivos": [], "comentario": ""}

    nota = _nota(d)
    motivos = []
    sentimiento = str(d.get("sentimiento", "")).casefold()
    grupos = [("problemas", PROBLEMA), ("aspectos_positivos", POSITIVO), ("aspectos_neutrales", NEUTRAL),
              ("aspectos", POSITIVO if not pd.isna(nota) and nota >= 4 else NEUTRAL),
              ("razones", POSITIVO if sentimiento == "positivo" else PROBLEMA if sentimiento == "negativo" else NEUTRAL)]
    for clave, grupo in grupos:
        motivos += [(e, grupo_de(e, grupo)) for e in map(etiqueta, _lista(d.get(clave)))]
    motivos += [(f"Opción {t}", NEUTRAL) for t in _lista(d.get("label_2"))]
    comentario = " · ".join(str(d[c]).strip() for c in ("problemas_otros", "aspectos_otros", "otro_motivo", "otros")
                            if str(d.get(c) or "").strip())
    return {"tipo": ENCUESTA, "calificacion": nota, "motivos": motivos, "comentario": comentario}


def _norm(nombre) -> str:
    return " ".join(str(nombre).casefold().split())


def _aplicar(leido: dict, conf: dict) -> dict:
    """Aplica la configuración de la campaña ({valor: (significado, sentido)}) a una respuesta interpretada."""
    def usar(valor, sentido):
        sig, sen = conf.get(valor, (None, None))
        return (sig or valor), (sen or sentido)

    nota, tipo = leido["calificacion"], leido["tipo"]
    sugeridos = {}
    if not pd.isna(nota):
        sugeridos[valor_nota(nota)] = sentido_nota(nota)
    for m, g in leido["motivos"]:
        sugeridos.setdefault(m, g)
    if tipo != ENCUESTA:
        sugeridos[tipo] = SENTIDO_TIPO.get(tipo, NEUTRAL)

    motivos = [usar(m, g) for m, g in leido["motivos"]]
    if not pd.isna(nota):
        sentido = usar(valor_nota(nota), sentido_nota(nota))[1]
    elif motivos:
        sentidos = {s for _, s in motivos}
        sentido = NEGATIVA if NEGATIVA in sentidos else POSITIVA if POSITIVA in sentidos else NEUTRAL
    elif tipo != ENCUESTA:
        sentido = usar(tipo, SENTIDO_TIPO.get(tipo, NEUTRAL))[1]
    else:
        sentido = NEUTRAL
    tipo_visible = usar(tipo, None)[0] if tipo != ENCUESTA else tipo
    return {"sugeridos": sugeridos, "motivos": motivos, "sentido": sentido, "tipo": tipo_visible}


def analizar(df: pd.DataFrame, significados: dict | None = None) -> pd.DataFrame:
    """Una fila por cliente que respondió, con la respuesta interpretada.

    significados: {(empresa, campaña normalizada): {valor: (significado, sentido)}} para los flujos
    propios de cada campaña (por ejemplo, "Opción 1" = "Sin señal", Negativa)."""
    columnas = ["empresa", "difusion", "telefono", "fecha", "tipo", "calificacion", "motivos", "grupos",
                "sentido", "sugeridos", "comentario", "respuesta"]
    if df.empty or "respuesta" not in df:
        return pd.DataFrame(columns=columnas)
    r = df[df["respuesta"].fillna("").str.strip() != ""]
    if r.empty:
        return pd.DataFrame(columns=columnas)
    significados = significados or {}
    leido = [interpretar(t) for t in r["respuesta"]]
    hecho = [_aplicar(x, significados.get((e, _norm(d)), {}))
             for x, e, d in zip(leido, r["empresa"], r["difusion"])]
    fecha = r["leido_en"].fillna(r["despachado_en"]) if "leido_en" in r else r["despachado_en"]
    return pd.DataFrame({
        "empresa": r["empresa"].values,
        "difusion": r["difusion"].values,
        "telefono": r["telefono"].values,
        "fecha": fecha.values,
        "tipo": [h["tipo"] for h in hecho],
        "calificacion": pd.array([x["calificacion"] for x in leido], dtype="Int64"),
        "motivos": [[m for m, _ in h["motivos"]] for h in hecho],
        "grupos": [dict(h["motivos"]) for h in hecho],
        "sentido": [h["sentido"] for h in hecho],
        "sugeridos": [h["sugeridos"] for h in hecho],
        "comentario": [x["comentario"] for x in leido],
        "respuesta": r["respuesta"].values,
    })


def valores_campana(a: pd.DataFrame, empresa: str, difusion: str, conf: dict | None = None) -> pd.DataFrame:
    """Valores que llegaron en una campaña, con cuántos clientes y su significado/sentido (guardado o sugerido)."""
    conf = conf or {}
    filas = a[(a["empresa"] == empresa) & (a["difusion"] == difusion)]
    cuenta, sugerido = {}, {}
    for sug in filas["sugeridos"]:
        for valor, sentido in sug.items():
            cuenta[valor] = cuenta.get(valor, 0) + 1
            sugerido.setdefault(valor, sentido)

    def orden(valor):
        if valor.startswith("Calificación "):
            return (0, valor)
        return (1 if valor not in TIPOS else 2, -cuenta[valor], valor)

    salida = []
    for valor in sorted(cuenta, key=orden):
        sig, sen = conf.get(valor, (None, None))
        salida.append({"Valor": valor, "Clientes": cuenta[valor], "Significado": sig or valor,
                       "Sentido": sen or sugerido[valor]})
    return pd.DataFrame(salida, columns=["Valor", "Clientes", "Significado", "Sentido"])


def tabla_campana(a: pd.DataFrame, empresa: str, difusion: str, conf: dict | None = None) -> pd.DataFrame:
    """Tabla de respuestas de UNA campaña para informes: qué respondieron, su sentido, cuántos y qué %."""
    v = valores_campana(a, empresa, difusion, conf)
    total = int(((a["empresa"] == empresa) & (a["difusion"] == difusion)).sum())
    if v.empty or not total:
        return pd.DataFrame(columns=["Respuesta", "Valor original", "Sentido", "Clientes", "% de los que respondieron"])
    v = v.assign(orden=v["Sentido"].map({s: i for i, s in enumerate(SENTIDOS)}))
    v = v.sort_values(["orden", "Clientes"], ascending=[True, False])
    return pd.DataFrame({
        "Respuesta": v["Significado"].values,
        "Valor original": [x if x != s else "" for x, s in zip(v["Valor"], v["Significado"])],
        "Sentido": v["Sentido"].values,
        "Clientes": v["Clientes"].values,
        "% de los que respondieron": (v["Clientes"] / total).map("{:.1%}".format).values,
    })


def lista_legible(a: pd.DataFrame) -> pd.DataFrame:
    """Tabla para personas: sin JSON, con columnas claras."""
    return pd.DataFrame({
        "Empresa": a["empresa"], "Campaña": a["difusion"], "Teléfono": a["telefono"],
        "Sentido": a["sentido"], "Tipo de respuesta": a["tipo"], "Calificación": a["calificacion"],
        "Motivos": a["motivos"].map(", ".join), "Comentario": a["comentario"],
        "Respuesta original": a["respuesta"], "Fecha": a["fecha"],
    }).reset_index(drop=True)
