#
# presentation.py — QUALITY CONTROL for how data is PRESENTED on a blank surface.
#
# Born from the 2026-08-10 incident (14:08:26 session). A Brain Worker did impeccable work —45 candidates compared,
# 3 proposals with round trips, prices, and surcharge for car height— and rendered it BADLY: three rich cards squeezed
# into two columns (one orphan in the last row), titles with three ideas inside wrapping to four lines and colliding
# with the price, and an important warning cut mid-word ("⚠️ Llevar tu c").
#
# The diagnosis was NOT "the model thinks it looks nice this way". It was that NOBODY was making the decision:
#   · `columns:2` was a model guess that OVERRAN the widget's own correct heuristic (3 cards → 1 column, i.e. the three
#     horizontal rows the operator expected);
#   · nobody had told the worker how much fits in a title — that information lived only in CSS;
#   · and our own `[:200]` cap silently cut text in the middle of a warning.
#
# Hence this module's three rules:
#
#   1. THE SURFACE OWNS LAYOUT. The filler describes CONTENT; how many columns, how they are distributed, and what
#      enters each row are decided by the widget from the SHAPE of the content. Layout is not a parameter to guess
#      wrong from outside.
#   2. BUDGETS ARE DECLARED, NOT GUESSED. Each blank surface publishes in its manifest how much fits in each field,
#      and that travels to the prompt of whoever will fill it. A model cannot respect a limit nobody told it.
#   3. SILENT CLIPPING IS FORBIDDEN. If something does not fit, cut on a word boundary, mark it with "...", and record
#      it as an incident. A warning cut mid-word is worse than omitting it.
#
# Intentionally GENERIC: it knows nothing about ferries, hotels, or results. A weather widget can remain a rigid,
# permanent format (does not declare `presentation` and nothing happens here); blank sheets that present findings,
# reports, or charts are the ones that need this flexibility WITH quality control.
#
from __future__ import annotations

# Default budgets for a readable card. Applied by surfaces that do not declare their own.
# Derived from measuring the real case: a 53-char title with three ideas wrapped to 4 lines and collided with the
# price; at ~34 it fits in one or two lines and breathes.
DEFAULTS: dict = {
    "sheet_title": 70,       # sheet header: WHAT it is about, not the whole task statement
    "sheet_subtitle": 220,   # one or two context/caveat sentences
    "title": 34,             # result name. ONE idea
    "subtitle": 70,          # one line of context
    "price": 16,             # highlighted label; never wraps
    "badge": 16,             # etiqueta corta
    "part_title": 40,        # the name of a component within a proposal
    "fact_label": 22,        # the left column of the data record
    "fact_value": 90,
}

# UNIVERSAL rules for presenting data on a blank surface. This is the preset that guarantees quality: it describes NO
# domain, only how information is distributed across cards so it can be read at a glance.
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
    """Field budgets for this surface: what its manifest declares over the defaults."""
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
    """Is this a BLANK surface (content decides its shape) or a rigid format?

    A weather widget is rigid: temperature, hours, icons, always the same — and that is fine. Presentation quality
    control only makes sense where the shape is decided on each delivery.
    """
    return bool((_manifest(widget_id).get("presentation") or {}).get("blank_sheet"))


def directive(widget_id: str = "") -> str:
    """Prompt block that guarantees presentation quality. Universal rules + this surface's REAL budgets. This is the
    only preset: formats remain free."""
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
    """BLANK surfaces from the catalog. Discovered by manifest, not by a hardcoded list: a new widget joins simply by
    declaring `presentation.blank_sheet`."""
    try:
        from widgets import runtime
        ids = [w.get("id") for w in (runtime.catalog() or [])]
    except Exception:
        return []
    return [i for i in ids if i and is_blank_sheet(i)]


def directive_for(text: str) -> str:
    """Presentation directive for the blank surfaces MENTIONED by this prompt.

    This lets quality control travel with the task without bloating every prompt: a worker that only needs to write a
    file does not receive card layout rules. And there is no per-widget wiring: if the prompt names a blank sheet, its
    budgets enter automatically.
    """
    low = (text or "").lower()
    hit = [w for w in blank_sheets() if w.lower() in low]
    if not hit:
        return ""
    return "\n\n".join(directive(w) for w in hit[:2])


def clip(text, limit: int) -> tuple[str, bool]:
    """Clip on a WORD boundary and mark the cut. Returns (text, was_clipped).

    Replaces scattered `str(x)[:N]`, which cut mid-word without saying so: that is how the real-case warning
    "⚠️ Llevar tu cadena..." was lost and became "⚠️ Llevar tu c".
    """
    s = "" if text is None else str(text).strip()
    if limit <= 0 or len(s) <= limit:
        return s, False
    cut = s[:limit]
    sp = cut.rfind(" ")
    if sp > limit * 0.6:          # there is a whole word to cut at; otherwise, a hard cut is better than one word
        cut = cut[:sp]
    return cut.rstrip(" ,;:·-") + "…", True


def audit(widget_id: str, payload: dict) -> list[str]:
    """Review a payload BEFORE rendering it and return presentation incidents in plain language.

    In code, not only in the prompt: a prompt is a request, not a guarantee. Output from here is recorded in
    observability (and can be returned to the worker for fixing), so a payload that breaks the card stops being
    invisible.
    """
    c = contract(widget_id)
    out: list[str] = []

    def _check(label: str, value, key: str, *, clipped: bool = False) -> None:
        """`clipped` distinguishes what is actually CLIPPED (the sheet header, which goes through `clip`) from what
        simply DOES NOT FIT and wraps, breaking the card. Saying "will be clipped" for a field that is actually kept
        whole would send people looking for data loss that does not exist."""
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

    # Comparing requires comparable columns: if one item has a price and another does not, the mental table breaks.
    if len(shapes) > 1:
        for idx, name in ((1, "price"), (2, "facts")):
            vals = {s[idx] for s in shapes}
            if len(vals) > 1:
                out.append(f"los items no tienen la MISMA forma: unos traen `{name}` y otros no — no se pueden comparar")
    return out
