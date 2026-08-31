"""V2-451 · the rows block depended on the TAB, so an errand without a browser showed none.

`_sheet_top_rows` resolves the sheet FROM the browser task, and `navegador_lines()` only composes cards if
there are tasks. An errand resolved by SEARCH has no tab: it fills the sheet and the prompt does not name a
single row — and it does not even emit the V2-438 warning, because it lives inside the function nobody calls.

Measured in `cheapest-monitor__us` (2026-08-28, 24/7 set):

    navegador_task_id: ""            ← there was no browser for the entire round
    results_sheet: 6 rows with name and price (Dell S2725QC, LG 27UP650-W, BenQ GW2790QT…)
    delivery_completeness: {named: 0, available: 6, shown_to_model: false}
    unresolved_errand_sheets: TODO down to zero — not even one warning

and the blocker judge: «it responded with an empty promise ("I'll get back to you") without delivering anything.
The results sheet already had 6». This is the cause left open since V2-432, V2-441, and V2-444: the sheet belongs
to the ERRAND (V2-259), and the prompt only knew how to read it through the browser.
"""
import pytest

from nucleo import dispatch as D
from nucleo.flash import live_blocks as LB
from nucleo.workers.session import SessionRecord
from widgets.navegador import tasks as T
from widgets.results import data as SHEET


@pytest.fixture(autouse=True)
def _clean():
    T._tasks.clear()
    D._SESSIONS.clear()
    yield
    T._tasks.clear()
    D._SESSIONS.clear()


def _encargo_sin_navegador(sheet="v451-1", filas=(("Dell S2725QC", "$280"), ("LG 27UP650-W", "$230"))):
    rec = SessionRecord(task_id="w1", goal="cheapest 4K monitor", kind="web")
    rec.status, rec.sheet = "running", sheet
    D._SESSIONS["w1"] = rec
    if filas:
        SHEET.apply_action("present", {"sheet": sheet, "title": "Resultados",
                                       "items": [{"title": t, "price": p} for t, p in filas]})
    return rec


def test_las_filas_de_su_hoja_llegan_al_prompt_SIN_pestana_de_navegador():
    _encargo_sin_navegador()
    st = "\n".join(LB.pending_task_lines())
    assert "YA ENTREGADO (de su hoja)" in st
    assert "Dell S2725QC — $280" in st and "LG 27UP650-W — $230" in st
    assert not T._tasks, "la premisa del caso es que NO hay tarea de navegador"


def test_sin_filas_no_se_dice_nada():
    """A block that always appears stops being read, and announcing an empty delivery is the lie of V2-209."""
    # OWN sheet: the store is shared between tests, so reusing the previous case's reads its rows and the
    # test fails for the wrong reason — confirmed, it failed that way when it was written.
    _encargo_sin_navegador(sheet="v451-vacia", filas=())
    assert "YA ENTREGADO (de su hoja)" not in "\n".join(LB.pending_task_lines())


def test_sin_hoja_sellada_no_se_inventa_ninguna():
    """An errand without a sheet reads the BARE box if allowed to, and that is the graveyard of previous rounds
(V2-281): it would show findings from ANOTHER errand as if they belonged to this one."""
    rec = SessionRecord(task_id="w1", goal="algo", kind="web")
    rec.status, rec.sheet = "running", ""
    D._SESSIONS["w1"] = rec
    SHEET.apply_action("present", {"sheet": "", "title": "Resultados",
                                   "items": [{"title": "Guitarra de otra ronda", "price": "100 €"}]})
    st = "\n".join(LB.pending_task_lines())
    assert "Guitarra de otra ronda" not in st


def test_una_fila_SIN_precio_lo_dice_en_vez_de_callarlo():
    """Same rule as `_sheet_top_rows` (V2-360): naming the gap costs one word and closes the
substitution — a name on its own is read as a comparable option."""
    _encargo_sin_navegador(filas=(("Monitor sin importe", ""),))
    assert "SIN PRECIO" in "\n".join(LB.pending_task_lines())


def test_el_resumen_del_encargo_LLEVA_su_hoja():
    """The plumbing: without the field in `pending_summaries`, the block has nothing to read, and the four above
would pass with only a partial fix."""
    rec = _encargo_sin_navegador()
    fila = next(x for x in D.pending_summaries() if x["id"] == "w1")
    assert fila.get("sheet") == rec.sheet


# ── AND THE INSTRUMENT MUST BE ABLE TO SEE IT ─────────────────────────────────────────────────────────────
# The fix put the rows in a NEW block with its own header, and `verify._rows_in` read only the browser header
# on the browser LINE. Measured on 2026-08-28: in the four rounds after the fix, `navegador_task_id` was EMPTY
# in all four, so `shown_to_model` would have been False forever and I would have concluded that the fix did not
# work. A fix the instrument cannot see cannot be verified — and here the instrument is me two hours earlier.
def test_el_ARNES_reconoce_la_cabecera_del_bloque_de_tareas():
    from tests.use_cases.e2e.agent.verify import _rows_in
    _encargo_sin_navegador(sheet="v451-arnes", filas=(("Dell S2725QC", "$280"), ("LG 27UP650-W", "$230")))
    sp = "\n".join(LB.pending_task_lines())
    assert _rows_in(sp) == ["Dell S2725QC", "LG 27UP650-W"], sp[:200]


def test_y_sigue_reconociendo_la_del_NAVEGADOR():
    """Sensitivity in the other direction: teaching it to read the new one must not cost the old one, which is
what measures all rounds with a browser."""
    from tests.use_cases.e2e.agent.verify import _ROWS_HEAD, _rows_in
    assert _rows_in(f"NAVEGADOR …{_ROWS_HEAD}«Bici Orbea — 150€». OJO: la hoja") == ["Bici Orbea"]


# ── A SINGLE FORMATTER (V2-455) ──────────────────────────────────────────────────────────────────────────
# V2-451 left TWO: the one for the browser card and the new one. Two copies of a rule drift apart without warning —
# this house has paid for it four times this week— and the rule they format has three tenants that each cost a
# round: the stated absence (V2-360), the phone as actionable data (V2-240), and the search hint that is NOT a
# candidate (V2-376).
def test_las_DOS_lecturas_formatean_la_fila_IGUAL():
    from nucleo.flash import live_blocks as _LB
    from nucleo.flash.errand_sheet import fila
    import inspect
    assert "fila(i)" in inspect.getsource(_LB._sheet_top_rows), (
        "la cara del navegador volvió a formatear por su cuenta")
    assert fila({"title": "X", "price": "10 €"}) == "«X — 10 €»"


def test_el_formateador_conserva_las_TRES_reglas_que_costaron_una_ronda_cada_una():
    from nucleo.flash.errand_sheet import fila
    assert fila({"title": "Fontanero", "tel": "600123456"}) == "«Fontanero — 600123456»"      # V2-240
    assert "SIN PRECIO" in fila({"title": "Monitor"})                                          # V2-360
    assert "aún no es un candidato" in fila(                                                   # V2-376
        {"title": "9 precios 2026", "facts": [{"label": "origen", "value": "búsqueda web"}]})


def test_el_TELEFONO_tambien_se_lee_de_los_facts():
    """It comes from both places depending on who extracts it; reading only one loses half."""
    from nucleo.flash.errand_sheet import fila
    assert "600111222" in fila({"title": "Cerrajero", "facts": [{"label": "Teléfono", "value": "600111222"}]})
