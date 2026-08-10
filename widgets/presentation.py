#
# presentation.py — CONTROL DE CALIDAD de cómo se PRESENTAN los datos en una superficie en blanco.
#
# Nace del incidente del 2026-08-10 (sesión 14:08:26). Un Brain Worker hizo un trabajo impecable —45 candidatos
# comparados, 3 propuestas con ida y vuelta, precios y sobrecoste por altura del coche— y lo pintó FEO: tres tarjetas
# ricas metidas en dos columnas (una huérfana en la última fila), títulos con tres ideas dentro que envolvían a cuatro
# líneas y chocaban con el precio, y un aviso importante cortado a media palabra («⚠️ Llevar tu c»).
#
# El diagnóstico NO fue «al modelo le parece bonito así». Fue que NADIE tomaba la decisión:
#   · el `columns:2` era una suposición del modelo que PISABA la heurística correcta del propio widget (3 tarjetas
#     → 1 columna, o sea las tres filas horizontales que el operador esperaba);
#   · nadie le había dicho al worker cuánto cabe en un título — esa información vivía solo en el CSS;
#   · y nuestro propio tope `[:200]` cortaba en silencio, en mitad de un aviso.
#
# De ahí las tres reglas de este módulo:
#
#   1. LA SUPERFICIE MANDA EN EL LAYOUT. Quien rellena describe el CONTENIDO; cuántas columnas, cómo se reparten y
#      qué entra en cada fila lo decide el widget a partir de la FORMA del contenido. El layout no es un parámetro
#      que se pueda adivinar mal desde fuera.
#   2. LOS PRESUPUESTOS SE DECLARAN, NO SE ADIVINAN. Cada superficie en blanco publica en su manifest cuánto cabe
#      en cada campo, y eso viaja al prompt de quien la va a rellenar. Un modelo no puede respetar un límite que
#      nadie le ha dicho.
#   3. RECORTAR EN SILENCIO ESTÁ PROHIBIDO. Si algo no cabe se corta por frontera de palabra, se marca con «…» y
#      queda registrado como incidencia. Un aviso cortado a media palabra es peor que no ponerlo.
#
# GENÉRICO a propósito: no sabe nada de ferries, hoteles ni resultados. Un widget del tiempo puede seguir siendo un
# formato rígido y permanente (no declara `presentation` y aquí no pasa nada); las hojas en blanco donde se presentan
# hallazgos, informes o gráficos son las que necesitan esta flexibilidad CON control de calidad.
#
from __future__ import annotations

# Presupuestos por defecto de una tarjeta legible. Son los que aplica una superficie que no declara los suyos.
# Salen de medir el caso real: un título de 53 chars con tres ideas dentro envolvía a 4 líneas y chocaba con el
# precio; a ~34 cabe en una o dos y respira.
DEFAULTS: dict = {
    "sheet_title": 70,       # cabecera de la hoja: DE QUÉ va, no el enunciado entero del encargo
    "sheet_subtitle": 220,   # una o dos frases de contexto/salvedades
    "title": 34,             # nombre del resultado. UNA idea
    "subtitle": 70,          # una línea de contexto
    "price": 16,             # etiqueta destacada; no envuelve nunca
    "badge": 16,             # etiqueta corta
    "part_title": 40,        # el nombre de una pieza dentro de una propuesta
    "fact_label": 22,        # la columna izquierda de la ficha de datos
    "fact_value": 90,
}

# Reglas UNIVERSALES de presentar datos en una superficie en blanco. Es el preset que garantiza la calidad: no
# describe NINGÚN dominio, solo cómo se reparte información en tarjetas para que se lea de un vistazo.
_UNIVERSAL = """PRESENTACIÓN (control de calidad — aplica SIEMPRE que rellenes una superficie de datos)
Tu trabajo no acaba con encontrar el dato: acaba cuando se LEE de un vistazo. Reglas:
· UNA IDEA POR CAMPO. El `title` es el NOMBRE del resultado y nada más. La ruta, la compañía, el barco, el horario
  o la duración NO van en el título: van en `subtitle` (una línea) o en `facts` (dato duro).
· RESPETA LOS PRESUPUESTOS de abajo. Son los que caben sin envolver. Pasarse no «cabe apretado»: rompe la tarjeta,
  choca con el precio y obliga a recortar, y lo recortado se pierde.
· LOS DATOS DUROS VAN EN `facts`, no en prosa. Precio, horario, duración, condiciones, medidas, valoración: cada
  uno su etiqueta y su valor. Así se comparan en columna y se pueden consultar después por voz.
· NO DECIDAS EL LAYOUT. No mandes número de columnas ni maquetes con guiones, saltos ni tablas ASCII: la superficie
  reparte el espacio según la forma de lo que le des, y lo hace mejor que una suposición a ciegas.
· NADA IMPORTANTE AL FINAL DE UN CAMPO LARGO. Si una salvedad o un aviso importa, va en su propio `fact` o en su
  propia línea — nunca colgando del final de un párrafo que puede quedarse sin sitio.
· MISMA FORMA PARA TODOS LOS ITEMS. Si uno lleva precio y horario, todos. Comparar exige columnas comparables."""


def _manifest(widget_id: str) -> dict:
    try:
        from widgets import runtime
        return runtime.get(widget_id) or {}
    except Exception:
        return {}


def contract(widget_id: str) -> dict:
    """Presupuestos de campo de esta superficie: lo que declare su manifest sobre los defaults."""
    declared = (_manifest(widget_id).get("presentation") or {}).get("budgets") or {}
    out = dict(DEFAULTS)
    for k, v in declared.items():
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if iv > 0:
            out[k] = iv
    return out


def is_blank_sheet(widget_id: str) -> bool:
    """¿Es una superficie EN BLANCO (su forma la decide el contenido) o un formato rígido?

    Un widget del tiempo es rígido: temperatura, horas, iconos, siempre igual — y está bien que lo sea. El control
    de calidad de presentación solo tiene sentido donde la forma se decide en cada entrega.
    """
    return bool((_manifest(widget_id).get("presentation") or {}).get("blank_sheet"))


def directive(widget_id: str = "") -> str:
    """El bloque de prompt que garantiza la calidad de presentación. Reglas universales + los presupuestos REALES
    de esta superficie. Es lo único que se presetea: los formatos siguen siendo libres."""
    lines = [_UNIVERSAL]
    if widget_id:
        c = contract(widget_id)
        lines.append(
            "\nPRESUPUESTOS de «%s» (caracteres que caben sin envolver):\n"
            "· título de la hoja ≤%d · subtítulo de la hoja ≤%d\n"
            "· title ≤%d · subtitle ≤%d · price ≤%d · badge ≤%d\n"
            "· título de pieza ≤%d · etiqueta de dato ≤%d · valor de dato ≤%d"
            % (widget_id, c["sheet_title"], c["sheet_subtitle"], c["title"], c["subtitle"],
               c["price"], c["badge"], c["part_title"], c["fact_label"], c["fact_value"])
        )
    return "\n".join(lines)


def blank_sheets() -> list[str]:
    """Superficies EN BLANCO del catálogo. Se descubren por su manifest, no por una lista hardcodeada: un widget
    nuevo entra solo declarando `presentation.blank_sheet`."""
    try:
        from widgets import runtime
        ids = [w.get("id") for w in (runtime.catalog() or [])]
    except Exception:
        return []
    return [i for i in ids if i and is_blank_sheet(i)]


def directive_for(text: str) -> str:
    """La directiva de presentación de las superficies en blanco que MENCIONE este prompt.

    Así el control de calidad viaja con la tarea sin engordar todos los prompts: un worker que solo tiene que
    escribir un fichero no recibe reglas de maquetación de tarjetas. Y no hay cableado por-widget: si el prompt
    nombra una hoja en blanco, sus presupuestos entran solos.
    """
    low = (text or "").lower()
    hit = [w for w in blank_sheets() if w.lower() in low]
    if not hit:
        return ""
    return "\n\n".join(directive(w) for w in hit[:2])


def clip(text, limit: int) -> tuple[str, bool]:
    """Recorta por frontera de PALABRA y marca el corte. Devuelve (texto, se_recortó).

    Sustituye a los `str(x)[:N]` sueltos, que cortaban a media palabra y sin decirlo: así se perdió el aviso
    «⚠️ Llevar tu cadena…» del caso real, que quedó en «⚠️ Llevar tu c».
    """
    s = "" if text is None else str(text).strip()
    if limit <= 0 or len(s) <= limit:
        return s, False
    cut = s[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:          # hay una palabra entera donde cortar; si no, mejor el corte duro que una palabra sola
        cut = cut[:sp]
    return cut.rstrip(" ,;:·-") + "…", True


def audit(widget_id: str, payload: dict) -> list[str]:
    """Revisa un payload ANTES de pintarlo y devuelve las incidencias de presentación en lenguaje llano.

    En código, no solo en el prompt: un prompt es una petición, no una garantía. Lo que salga de aquí se registra
    en la observabilidad (y se le puede devolver al worker para que lo arregle), así que un payload que rompe la
    tarjeta deja de ser invisible.
    """
    c = contract(widget_id)
    out: list[str] = []

    def _check(label: str, value, key: str, *, clipped: bool = False) -> None:
        """`clipped` distingue lo que de verdad se RECORTA (la cabecera de la hoja, que pasa por `clip`) de lo que
        simplemente NO CABE y envuelve rompiendo la tarjeta. Decir «se recortará» de un campo que en realidad se
        conserva entero mandaría a buscar una pérdida de datos que no existe."""
        s = "" if value is None else str(value).strip()
        if s and len(s) > c[key]:
            what = "se recortará" if clipped else "envolverá y descuadrará la tarjeta"
            out.append(f"{label}: {len(s)} caracteres, caben {c[key]} — {what} («{s[:40]}…»)")

    _check("título de la hoja", payload.get("title"), "sheet_title", clipped=True)
    _check("subtítulo de la hoja", payload.get("subtitle"), "sheet_subtitle", clipped=True)

    if payload.get("columns") is not None:
        out.append("`columns` viene en el payload: el layout lo decide la superficie según la forma del contenido, "
                   "no quien la rellena — se ignora como orden y se trata como tope máximo")

    items = payload.get("items")
    items = items if isinstance(items, list) else []
    shapes = []
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict):
            continue
        _check(f"item {n} · title", it.get("title"), "title")
        _check(f"item {n} · subtitle", it.get("subtitle"), "subtitle")
        _check(f"item {n} · price", it.get("price"), "price")
        _check(f"item {n} · badge", it.get("badge"), "badge")
        for p in (it.get("parts") or []):
            if isinstance(p, dict):
                _check(f"item {n} · pieza «{str(p.get('kind') or '')[:12]}»", p.get("title"), "part_title")
        shapes.append((bool(it.get("parts")), bool(it.get("price")), bool(it.get("facts"))))

    # Comparar exige columnas comparables: si un item trae precio y otro no, la tabla mental se rompe.
    if len(shapes) > 1:
        for idx, name in ((1, "price"), (2, "facts")):
            vals = {s[idx] for s in shapes}
            if len(vals) > 1:
                out.append(f"los items no tienen la MISMA forma: unos traen `{name}` y otros no — no se pueden comparar")
    return out
