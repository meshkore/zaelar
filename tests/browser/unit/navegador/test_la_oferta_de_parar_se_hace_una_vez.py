"""V2-454 · the offer to stop a stuck task was repeated turn after turn.

The block said “if a task becomes STUCK or NOT PROGRESSING, say so in those exact words **the first time** it
comes up and offer to stop it,” and the model **cannot know whether it is the first time**: that is OUR fact, the
same lesson that V2-224 learned with the death notice. Without telling it, the offer is rendered on EVERY
turn while the task remains stuck.

Measured across the 334 saved rounds: **49 (14%) repeat the offer to stop two or more times**, including ten of
the last fifteen on 2026-08-28. The harm is not redundancy — **the operator ALREADY ANSWERED**: in
`search-buy-used-car` (10:57) they said “stop it and try again, or we can look somewhere else; you decide,” and
the next turn posed the same dilemma again; the judge classified it as a blocker [high].

And the rule governing the wording is V2-224’s: **silencing the repetition is not silencing the state.**
"""
import pytest

from nucleo import dispatch as D
from nucleo import turn_marks
from nucleo.flash import task_block as TB
from nucleo.workers.session import SessionRecord


@pytest.fixture(autouse=True)
def _clean():
    D._SESSIONS.clear()
    turn_marks._STALL_OFFERED.clear()
    yield
    D._SESSIONS.clear()
    turn_marks._STALL_OFFERED.clear()


def _atascada(tid="w1"):
    import time
    rec = SessionRecord(task_id=tid, goal="busca un fontanero", kind="web")
    rec.status = "running"
    rec.started = time.time() - 900
    rec.last_event_at = time.time() - 900          # STUCK: no signal
    D._SESSIONS[tid] = rec
    return rec


def test_la_PRIMERA_vez_se_ofrece_parar():
    _atascada()
    st = "\n".join(TB.pending_task_lines())
    assert "ENCALLADA" in st
    assert "YA le ofreciste" not in st


def test_la_SEGUNDA_vez_se_dice_que_NO_lo_vuelva_a_preguntar():
    _atascada()
    TB.pending_task_lines()                        # turn 1: it carries the offer forward
    st = "\n".join(TB.pending_task_lines())        # turn 2
    assert "YA le ofreciste pararla" in st and "NO se lo vuelvas a preguntar" in st


def test_pero_el_HECHO_se_sigue_diciendo():
    """The V2-224 rule: silencing the repetition is NOT silencing the state. If removing the offer also removed
    the fact, the turn would revert to “still running” — the silence that V2-131 closed off."""
    _atascada()
    TB.pending_task_lines()
    st = "\n".join(TB.pending_task_lines())
    assert "ENCALLADA" in st and "SIN DAR NINGUNA SEÑAL" in st


def test_una_tarea_SANA_no_marca_nada():
    """Sensitivity: if it were always marked, the first task that actually got stuck would already start as
    “offered,” and no one would ever offer to stop anything for it."""
    import time
    rec = SessionRecord(task_id="w2", goal="algo", kind="web")
    rec.status, rec.started, rec.last_event_at = "running", time.time(), time.time()
    D._SESSIONS["w2"] = rec
    TB.pending_task_lines()
    assert D.stall_offered("w2") == 0


def test_cada_tarea_lleva_su_propia_cuenta():
    """Two stuck assignments mean two offers: sharing the marker would leave the second one without anyone
    offering it anything."""
    _atascada("w1"); _atascada("w3")
    TB.pending_task_lines()
    assert D.stall_offered("w1") == 1 and D.stall_offered("w3") == 1


def test_el_bloque_le_DICE_al_modelo_que_no_repita_la_pregunta():
    """The instruction, not just the marker: without the phrase, the model has the fact and does not know what
    to do with it."""
    _atascada()
    st = "\n".join(TB.pending_task_lines())
    assert "la pregunta NO se \nrepite" in st or "la pregunta NO se repite" in st.replace("\n", "")
