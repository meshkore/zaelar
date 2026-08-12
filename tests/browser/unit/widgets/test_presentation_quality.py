#
# test_presentation_quality.py — CONTROL DE CALIDAD de cómo se PRESENTAN los datos en una superficie en blanco.
#
# Anclado al incidente del 2026-08-10 (sesión 14:08:26). El Brain Worker hizo un trabajo impecable —45 candidatos
# comparados, 3 propuestas con ida y vuelta y hasta el sobrecoste por altura del 4x4— y lo pintó ilegible:
#   · `columns: 2` con 3 tarjetas RICAS → una huérfana en la última fila, cuando lo correcto era 1 columna
#     (tres filas horizontales). El widget YA tenía esa heurística: el parámetro del payload la pisaba.
#   · títulos de 53 chars con tres ideas dentro («ruta · compañía · (barco)») → 4 líneas envueltas chocando
#     con el precio.
#   · y nuestro propio `[:200]` cortó un aviso a media palabra: «⚠️ Llevar tu c».
#
# El diagnóstico NO fue «al modelo le parece bonito así»: fue que nadie tomaba la decisión de layout y nadie le
# había dicho al worker los presupuestos, que vivían solo en el CSS. Esto fija los tres mecanismos.
#
import json
import pathlib

import pytest

WIDGET = pathlib.Path("widgets/results")

# El payload REAL que produjo la pantalla fea (medido del estado guardado).
REAL_SUBTITLE = ("Comparadas Baleària, GNV y Trasmed en Denia y Valencia. Solo la ruta DENIA tiene ferry rápido "
                 "(2h15). Precios ORIENTATIVOS de agosto punta: el final lo da el motor de reserva con tasas. "
                 "⚠️ Llevar tu cadena de seguridad y documentación del vehículo.")
REAL_PAYLOAD = {
    "title": "Ferry a Ibiza · Ida lun 17 ago · Vuelta vie 21 ago 2026 · 2 adultos + 2 niños (9 y 11) + coche 4x4 "
             "(5,0 m / 1,80 m)",
    "subtitle": REAL_SUBTITLE,
    "columns": 2,
    "items": [
        {"title": "⭐ Dénia ↔ Ibiza · Baleària RÁPIDO (Eleanor Roosevelt)",
         "subtitle": "El ÚNICO ferry rápido de las dos rutas · 2 h 15 m · salida diurna · diario en agosto",
         "price": "≈ 560–600 € ida+vuelta", "badge": "MEJOR OPCIÓN",
         "parts": [{"kind": "Ida", "title": "Baleària rápido · Dénia → Ibiza · lun 17 ago"}],
         "facts": {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6, "g": 7, "h": 8}},
    ],
}


# ── 1. Recortar en silencio está prohibido ────────────────────────────────────────────────────────────────────────

def test_the_warning_that_got_cut_mid_word_now_survives():
    """`[:200]` dejó «⚠️ Llevar tu c». Una salvedad amputada engaña más que su ausencia."""
    from widgets import presentation
    assert REAL_SUBTITLE[:200].endswith("Llevar tu c")      # así era antes
    out, cut = presentation.clip(REAL_SUBTITLE, 220)
    assert cut is True
    assert not out.endswith("Llevar tu c")
    assert out.endswith("…"), "un corte tiene que VERSE"
    assert "cadena de seguridad" in out, "debe cortar por palabra, no por carácter"


def test_clip_leaves_short_text_untouched():
    from widgets import presentation
    assert presentation.clip("corto", 220) == ("corto", False)
    assert presentation.clip(None, 220) == ("", False)


def test_clip_never_leaves_a_dangling_separator():
    from widgets import presentation
    out, _ = presentation.clip("Baleària rápido · Dénia → Ibiza · lunes diecisiete", 22)
    assert not out.rstrip("…").endswith(("·", ",", "-", ":", ";", " "))


# ── 2. El layout lo decide la SUPERFICIE, por la forma del contenido ──────────────────────────────────────────────

# El hueco de la rejilla lo define el CSS (`--s3`) y `gridStyle` lo lee de ahí: la réplica hace lo mismo leyéndolo
# del fichero, para que subir la escala no deje este test midiendo otra cosa que el widget.
def _gap():
    import re
    src = (WIDGET / "widget.js").read_text()
    m = re.search(r"--s3:\s*(\d+(?:\.\d+)?)px", src)
    return float(m.group(1)) if m else 12.0


_GAP = _gap()


def _grid(items, cap=None):
    """Réplica de `widget.js::gridStyle` — devuelve `(ancho mínimo de columna, tope de columnas)`.

    Desde 2026-08-12 el reparto ya NO es un número fijo calculado en JS: la tarjeta es REDIMENSIONABLE (y puede
    maximizarse), así que quien manda es el ancho REAL. La superficie declara dos cosas —cuánto necesita como
    mínimo una tarjeta de esa riqueza, y cuántas columnas como máximo tienen sentido— y el CSS reparte. La
    garantía que se comprueba abajo es la misma de siempre: el contenido rico no se estrangula y el payload
    solo puede REDUCIR."""
    rich = any((it.get("parts") or it.get("images") or it.get("blocks")
                or len(it.get("facts") or []) > 3 or len(it.get("lines") or []) > 4) for it in items)
    medium = not rich and any((it.get("lines") or it.get("image") or it.get("facts")) for it in items)
    min_w = 400 if rich else 300 if medium else 230
    max_cols = 2 if rich else 3 if medium else 4
    if cap and int(cap) >= 1:
        max_cols = min(max_cols, int(cap))
    return min_w, max(1, max_cols)


def _columns_at(items, width, cap=None):
    """Cuántas columnas SALEN de verdad a un ancho de tarjeta dado (lo que hace `auto-fill` + `minmax`)."""
    min_w, max_cols = _grid(items, cap)
    floor = (width - (max_cols - 1) * _GAP) / max_cols
    track = max(min(width, min_w), floor)
    return max(1, min(max_cols, int((width + _GAP) // (track + _GAP))))


def test_the_real_case_now_renders_as_three_horizontal_rows():
    """Lo que pidió el operador: «esto yo lo hubiera presentado en tres filas horizontales». Sigue saliendo así,
    pero ahora por una razón comprobable —no caben dos tarjetas de 400px en una hoja de 720— en vez de por una
    regla de huérfanas escrita a mano."""
    rich = [{"parts": [1, 2], "facts": [1] * 8}] * 3
    assert _columns_at(rich, 720, cap=2) == 1, "3 propuestas ricas en la hoja por defecto = 1 columna"


def test_widening_the_sheet_uses_the_space_instead_of_wasting_it():
    """Y esta es la razón de ser del cambio: si el operador la agranda o la maximiza, las mismas tres propuestas
    se ponen en paralelo. Con el número de columnas fijo, maximizar solo estiraba una columna."""
    rich = [{"parts": [1, 2], "facts": [1] * 8}] * 3
    assert _columns_at(rich, 1600) == 2, "hay sitio para dos columnas de 400: úsalo"
    assert _columns_at([{}] * 8, 1600) == 4, "tarjetas simples aprovechan más, pero con tope"


def test_a_payload_hint_can_only_reduce_never_force():
    """`columns` es un TOPE. Antes MANDABA y pisaba la decisión correcta de la superficie."""
    assert _grid([{}] * 8)[1] == 4
    assert _grid([{}] * 8, cap=2)[1] == 2, "puede reducir"
    assert _grid([{"parts": [1]}] * 4, cap=3)[1] == 2, "no puede forzar columnas sobre contenido rico"


def test_rich_content_is_never_squeezed_however_narrow_the_card_gets():
    """El fallo original («Valenci / a → / Palma»): una tarjeta rica en una columna estrecha. Ahora es imposible
    por construcción — a cualquier ancho por debajo de dos columnas de 400px solo cabe una."""
    rich = [{"parts": [1, 2]}] * 4
    for width in (320, 480, 620, 720, 800):
        assert _columns_at(rich, width) == 1


def test_the_gap_has_a_single_source_of_truth():
    """Tenerlo dos veces costó una columna: al subir la rejilla de 12 a 14px, `gridStyle` siguió restando 12, el
    suelo de cada pista quedó 2px por encima de lo que cabía y `auto-fill` bajó de dos columnas a UNA en una hoja
    de 1.420px. Se ve como «maximizar ya no aprovecha el ancho» y no se deduce leyendo el diff."""
    src = (WIDGET / "widget.js").read_text()
    fn = src[src.index("function gridStyle("):src.index("function makeCard(")]
    assert "var(--s3)" in fn, "el hueco sale de la variable que lo pinta"
    import re
    assert not re.search(r"const gap\s*=\s*\d", fn), "un número copiado aquí se desincroniza del CSS en silencio"


def test_the_widget_really_delegates_the_layout():
    src = (WIDGET / "widget.js").read_text()
    assert "function gridStyle(" in src
    assert "gridStyle(rest, primary.length ? 2 : data.columns)" in src, \
        "el grid debe pasar por la función, no por data.columns pelado"
    assert "Math.min(3, data.columns ||" not in src, "esa era la forma en la que el payload MANDABA"
    assert "auto-fill" in src, "el reparto lo hace el ancho REAL, no un número calculado al pintar"


# ── 3. Los presupuestos se declaran, no se adivinan ───────────────────────────────────────────────────────────────

def test_the_blank_sheet_declares_its_contract():
    m = json.loads((WIDGET / "manifest.json").read_text())
    pres = m.get("presentation") or {}
    assert pres.get("blank_sheet") is True
    for k in ("title", "subtitle", "price", "badge", "sheet_title", "part_title"):
        assert k in (pres.get("budgets") or {}), f"falta el presupuesto de {k}"


def test_a_rigid_widget_is_not_subject_to_this():
    """Un widget del tiempo puede seguir siendo un formato fijo: no declara nada y aquí no pasa nada."""
    from widgets import presentation
    assert presentation.is_blank_sheet("clock") is False
    assert presentation.is_blank_sheet("no-existe") is False
    assert presentation.contract("no-existe") == presentation.DEFAULTS


def test_blank_sheets_are_discovered_from_manifests_not_a_hardcoded_list():
    from widgets import presentation
    sheets = presentation.blank_sheets()
    assert "results" in sheets
    assert "clock" not in sheets
    src = pathlib.Path("widgets/presentation.py").read_text()
    assert '"results"' not in src, "el módulo debe ser agnóstico del catálogo"


# ── 4. La directiva es el PRESET que garantiza la calidad, y viaja con la tarea ────────────────────────────────────

def test_the_directive_carries_the_real_budgets():
    from widgets import presentation
    d = presentation.directive("results")
    assert "UNA IDEA POR CAMPO" in d
    assert "NO DECIDAS EL LAYOUT" in d
    assert "title ≤34" in d, "los presupuestos REALES del widget, no una regla genérica vacía"


def test_the_directive_is_domain_agnostic():
    """Mecanismo genérico: sirve para propuestas de viaje, para un informe o para un gráfico."""
    from widgets import presentation
    d = presentation.directive("results").lower()
    for domain in ("ferry", "hotel", "vuelo", "ibiza", "viaje"):
        assert domain not in d


def test_it_only_reaches_prompts_that_will_display_data():
    from widgets import presentation
    assert presentation.directive_for("Escribe un fichero con el resumen.") == ""
    assert "PRESUPUESTOS" in presentation.directive_for(
        "entrega con `python -m nucleo.widget_cli data results present @informe.json`")


def test_the_worker_prompt_wires_it_in():
    import inspect
    from nucleo import dispatch
    src = inspect.getsource(dispatch)
    assert "_with_presentation" in src
    assert src.count("_with_presentation(") >= 3, "el genérico Y el de web, más la definición"


# ── 5. Un payload que rompe la tarjeta deja RASTRO (un prompt no es una garantía) ─────────────────────────────────

def test_the_audit_catches_every_defect_of_the_real_payload():
    from widgets import presentation
    issues = presentation.audit("results", REAL_PAYLOAD)
    joined = " | ".join(issues)
    assert "título de la hoja" in joined
    assert "subtítulo de la hoja" in joined
    assert "`columns`" in joined
    assert "item 1 · title" in joined
    assert "item 1 · price" in joined
    assert "pieza" in joined


def test_the_audit_is_honest_about_what_actually_happens():
    """La cabecera de la hoja SÍ se recorta; un título de item se conserva entero y ENVUELVE. Decir «se recortará»
    de algo que no se recorta manda a buscar una pérdida de datos inexistente."""
    from widgets import presentation
    issues = presentation.audit("results", REAL_PAYLOAD)
    sheet = next(i for i in issues if i.startswith("título de la hoja"))
    item = next(i for i in issues if i.startswith("item 1 · title"))
    assert "se recortará" in sheet
    assert "envolverá" in item and "se recortará" not in item


def test_the_audit_flags_items_that_cannot_be_compared():
    from widgets import presentation
    issues = presentation.audit("results", {"items": [{"title": "A", "price": "10€"}, {"title": "B"}]})
    assert any("MISMA forma" in i for i in issues)


def test_a_clean_payload_raises_nothing():
    from widgets import presentation
    clean = {"title": "Ferries a Ibiza · 17-21 ago",
             "subtitle": "45 opciones comparadas en Baleària, GNV y Trasmed.",
             "items": [{"title": "Baleària rápido", "subtitle": "Dénia → Ibiza · 2 h 15 m",
                        "price": "560 €", "badge": "MEJOR", "facts": {"Ida": "11:30"}},
                       {"title": "Baleària nocturno", "subtitle": "Valencia → Ibiza · 6 h",
                        "price": "340 €", "badge": "MÁS BARATO", "facts": {"Ida": "23:00"}}]}
    assert presentation.audit("results", clean) == []


def test_present_reports_its_presentation_issues_back(monkeypatch, tmp_path):
    """Las incidencias vuelven en la respuesta de la acción: así el worker puede corregir sin que el operador
    tenga que opinar sobre el diseño."""
    from widgets import store
    from widgets.results import data as rd

    saved = {}
    monkeypatch.setattr(store, "save", lambda wid, d: saved.setdefault(wid, d) or d)
    monkeypatch.setattr(rd.store, "save", lambda wid, d: saved.setdefault(wid, d) or d)

    out = rd.apply_action("present", dict(REAL_PAYLOAD))
    assert out["ok"] is True
    assert out["presentation"], "un payload que rompe la tarjeta no puede pasar en silencio"
    # y la cabecera guardada ya viene recortada por palabra, con marca
    assert saved["results"]["title"].endswith("…")


@pytest.mark.parametrize("action", ["present", "append"])
def test_both_fill_actions_are_audited(action):
    import inspect
    from widgets.results import data as rd
    src = inspect.getsource(rd.apply_action)
    body = src[src.index(f'if action == "{action}"'):]
    assert "_audit(payload)" in body[:400], f"{action} debe auditar su payload"
