"""V2-345 — what the worker NARRATES is the richest signal we have, and it was not appearing on any screen.

Measured in session `7575e81a` (2026-08-26), during the 21.6 min car assignment: **82 narrations, one every
16 s**, all sent to observability and none to the Process tab. They are better than any sentence we could
generate ourselves because they contain the site, the price, the model, and the REASON for the next step:

    «Wallapop devuelve candidatos pero mayormente coches viejos (pre-2016). Necesito filtros de año.»
    «¡Bien! Tengo más opciones dentro del presupuesto. Voy a revisar el Renault Laguna Coupé (11.650€).»

Frequency delivered to the tab, measured by REPLAY on that same session:

    antes de nada …………………………… una línea cada 162 s
    con V2-343 (pasos del navegador) … una línea cada  59 s
    con esto ………………………………………… una línea cada  10 s

The “💬” is NOT decoration. The worker MAKES claims, and this house has already paid the price for one of its
claims being taken as a verified fact (V2-249: it wrote “Reminder SCHEDULED” to durable memory without being able
to schedule anything). In this ring its prose coexists with what we HAVE verified —“14 results on the page”— so
they must be distinguishable at a glance. Adding a prefix instead of inventing a new channel is the pattern the
chat wall already uses.
"""
import pytest

from nucleo import sheets as SH


class _Rec:
    def __init__(self, tid="t1"):
        self.task_id, self.phases, self.surface = tid, [], ""


def test_the_worker_prose_is_marked_apart_from_verified_fact():
    """What distinguishes a worker claim from one of our facts must be visible without reading it."""
    r = _Rec()
    SH.record_phase(r, "14 resultados en la página", 150)
    SH.record_phase(r, "💬 ¡Tengo resultados! Veo varios coches diésel dentro del presupuesto.", 150)
    dichas = [p["s"] for p in r.phases]
    assert not dichas[0].startswith("💬"), "a fact we verified ourselves is not marked as said by it"
    assert dichas[1].startswith("💬")


def test_two_different_narrations_both_get_through():
    """They are almost always different —each one describes another step— so deduplication does not get in their way."""
    r = _Rec()
    SH.record_phase(r, "💬 Aplico el filtro de precio máximo 12.000€.", 150)
    SH.record_phase(r, "💬 El filtro no se aplicó por URL. Uso el filtro visual.", 150)
    assert len(r.phases) == 2


def test_the_same_narration_twice_is_still_ONE_line():
    """REGRESSION CHECK: deduplication still rules. A worker repeating itself is not progress."""
    r = _Rec()
    for _ in range(3):
        SH.record_phase(r, "💬 Sigo haciendo scroll para llegar a los resultados.", 150)
    assert len(r.phases) == 1


def test_a_whole_errand_fits_in_the_ring():
    """The measured assignment produces 127 lines. With the ring set to 40, the tab's closing sentence —“This is what it
    did to get here”— stopped being true by the end, which is when it is read most."""
    assert SH.PHASES_KEPT >= 127, "the ring must fit a real measured assignment, not a round number"
    r = _Rec()
    for i in range(127):
        SH.record_phase(r, f"💬 paso {i}", SH.PHASES_KEPT)
    assert len(r.phases) == 127


def test_the_ring_is_still_a_ring():
    """REGRESSION CHECK in the other direction: raising the limit must not turn into storing everything. This is what the
    operator SEES; the full audit lives in observability, with its evidence."""
    r = _Rec()
    for i in range(SH.PHASES_KEPT + 25):
        SH.record_phase(r, f"💬 paso {i}", SH.PHASES_KEPT)
    assert len(r.phases) == SH.PHASES_KEPT


def test_the_session_actually_pushes_it():
    """WIRING GUARD on the source WITHOUT comments: the no-caller decision is the fix that does not exist
    (V2-199), and this file found the code exactly in that state — `_emit_note` carried the good text
    to observability and nowhere else.

    V2-346: emission moved ENTIRELY to `progress.narration_out` (the architecture ratchet called for extraction,
    not raising the limit in `session.py`), so the guard checks BOTH places — that the session calls it, and that what
    is called keeps pushing to the ring. Checking only one gives a green result with the other empty."""
    from pathlib import Path

    def _limpio(ruta):
        return "\n".join(ln for ln in Path(ruta).read_text().splitlines()
                          if not ln.strip().startswith("#"))
    ses = _limpio("nucleo/workers/session.py")
    i = ses.index("def _emit_note")
    assert "_progress.narration_out(" in ses[i:i + 2600], "the session no longer calls it: the narration stays inside"
    prog = _limpio("nucleo/workers/progress.py")
    j = prog.index("def narration_out")
    cuerpo = prog[j:j + 2600]
    assert "record_phase" in cuerpo, "the narration does not reach the screen"
    assert 'emit("task", "💬 worker"' in cuerpo, "the narration no longer reaches the viewer"
    assert '"💬 "' in cuerpo, "without the marker, its claim reads as a verified fact"
