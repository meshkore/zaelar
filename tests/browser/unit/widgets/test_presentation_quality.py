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

def _columns_for(items, cap=None):
    """Réplica de `widget.js::columnsFor` (los tests de frontend son contratos de string, no ejecutan JS).
    El test de abajo verifica que la implementación real sigue teniendo esta forma."""
    rich = any((it.get("parts") or it.get("images")
                or len(it.get("facts") or []) > 3 or len(it.get("lines") or []) > 4) for it in items)
    cols = 1 if rich else (3 if len(items) > 6 else 2 if len(items) > 3 else 1)
    if cap and cap >= 1:
        cols = min(cols, int(cap))
    cols = max(1, min(3, cols))
    if cols > 1 and len(items) < cols * 2:
        cols = 1
    return cols


def test_the_real_case_now_renders_as_three_horizontal_rows():
    """Lo que pidió el operador: «esto yo lo hubiera presentado en tres filas horizontales»."""
    rich = [{"parts": [1, 2], "facts": [1] * 8}] * 3
    assert _columns_for(rich, cap=2) == 1, "3 propuestas ricas = 1 columna, pese al columns:2 del payload"


def test_a_payload_hint_can_only_reduce_never_force():
    """`columns` pasa a ser TOPE. Antes MANDABA y pisaba la heurística correcta del widget."""
    simple = [{}] * 8
    assert _columns_for(simple) == 3
    assert _columns_for(simple, cap=2) == 2, "puede reducir"
    assert _columns_for([{"parts": [1]}] * 4, cap=3) == 1, "no puede forzar columnas sobre contenido rico"


def test_no_unbalanced_orphan_card():
    assert _columns_for([{}] * 3) == 1      # 2+1 se lee como error de maquetación
    assert _columns_for([{}] * 4) == 2      # 2+2 cuadra


def test_a_normal_incomplete_last_row_is_left_alone():
    """El bug que NO queremos introducir: bajar 7 tarjetas a una columna sería peor que la huérfana."""
    assert _columns_for([{}] * 7) == 3
    assert _columns_for([{}] * 5) == 2


def test_the_widget_really_delegates_the_layout():
    src = (WIDGET / "widget.js").read_text()
    assert "function columnsFor(" in src
    assert "columnsFor(rest, data.columns)" in src, "el grid debe pasar por la función, no por data.columns pelado"
    assert "Math.min(3, data.columns ||" not in src, "esa era la forma en la que el payload MANDABA"


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
