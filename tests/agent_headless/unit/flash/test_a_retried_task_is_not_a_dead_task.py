"""V2-222 — the prompt was arguing with itself, and the turn picked the true half.

The harness counted, in `hotel-under-15-days`, 0 of 13 turns saying a background task had failed, against 3 of 3
for anything pushed as a system note, and concluded that the turn obeys what is PUSHED and ignores what is
RENDERED. The count is right. The reading was incomplete, and reading the whole system prompt of the eight turns
of sandbox `20260820-194231` shows why — seven of them carried the SAME errand twice:

    TAREAS DE FONDO EN CURSO (… NO reinicies ni digas que ya está): «Busca hoteles de 4 estrellas…»
        — abriendo una página… [paso 2/5, 40%] (llevas 64s)
    TAREAS DE FONDO — YA ACABADAS: «Busca hoteles de 4 estrellas…» FALLÓ … DÍSELO EN ESTE TURNO

The first attempt failed, `_remember_ended` filed it, V2-049 relaunched the same errand under a new id, and for
the next five minutes both blocks were telling the truth about different sessions while the operator had ONE
errand. «Sigo esperando resultados» was the accurate answer. No rewording of either half could have fixed it,
which is why V2-221's imperative measured 0/7 in the very round that carried it.

So this closes two things: a task that is about to retry itself is not recorded as ended (the source), and a task
whose goal is running right now is never reported as ended (the belt — a repeated escalation does it too). And
THEN, for a task that really did die, the notice goes out by the path that measured 3/3.
"""
import pytest

from nucleo import dispatch as d
from voice import brain_notes


class _Rec:
    def __init__(self, tid, goal, status="error", ok=False, summary=""):
        self.task_id, self.goal, self.status, self.ok, self.result_summary = tid, goal, status, ok, summary


@pytest.fixture(autouse=True)
def _clean():
    """Process-level registries: emptied around each test so one never sees another's leftovers."""
    e, s, n = dict(d._ENDED_SESSIONS), dict(d._SESSIONS), list(brain_notes._pending)
    d._ENDED_SESSIONS.clear(); d._SESSIONS.clear(); brain_notes.drain()
    yield
    d._ENDED_SESSIONS.clear(); d._ENDED_SESSIONS.update(e)
    d._SESSIONS.clear(); d._SESSIONS.update(s)
    brain_notes.drain(); brain_notes._pending.extend(n)


GOAL = "Busca hoteles de 4 estrellas para 2 personas, 4 noches, con "


def test_a_task_about_to_retry_is_NOT_filed_as_ended():
    d._remember_ended(_Rec("1", GOAL), resuming=True)
    assert d.recently_ended_sessions() == []


def test_and_it_does_not_tell_the_operator_it_died_either():
    """The worse half: «está esperando un resultado que ya no va a llegar» about an errand that IS coming back is
    a false statement we would have manufactured ourselves."""
    d._remember_ended(_Rec("1", GOAL), resuming=True)
    assert brain_notes.drain() == []


def test_the_MEASURED_contradiction_cannot_be_built_any_more():
    """Reproduces the shape of the seven turns: same goal, one session live, one filed as ended."""
    d._SESSIONS["2"] = _Rec("2", GOAL, status="running", ok=False)
    d._remember_ended(_Rec("1", GOAL))
    assert [r["goal"] for r in d.recently_ended_sessions()] == []


def test_a_DIFFERENT_errand_still_reports_its_death():
    """Sensitivity, and the reason the filter matches on the goal and not on «is anything running»: a live task
    must not silence the end of an unrelated one."""
    d._SESSIONS["2"] = _Rec("2", "reserva mesa en Casa Lucio", status="running")
    d._remember_ended(_Rec("1", GOAL))
    assert [r["goal"] for r in d.recently_ended_sessions()] == [GOAL.strip()]


def test_a_session_that_ALREADY_ended_does_not_mask_anything():
    """`_SESSIONS` keeps records until the `finally` pops them; only the LIVE states count as running."""
    d._SESSIONS["2"] = _Rec("2", GOAL, status="done", ok=True)
    d._remember_ended(_Rec("1", GOAL))
    assert len(d.recently_ended_sessions()) == 1


def test_a_task_that_really_died_is_PUSHED_not_only_rendered():
    d._remember_ended(_Rec("1", GOAL))
    notes = brain_notes.drain()
    assert len(notes) == 1
    assert "MUERTO" in notes[0] and GOAL[:40] in notes[0]
    assert "no se va a reintentar sola" in notes[0]


def test_the_pushed_notice_forbids_the_phrase_that_was_measured():
    d._remember_ended(_Rec("1", GOAL))
    assert "sigo con ello" in brain_notes.drain()[0]


@pytest.mark.parametrize("rec", [
    _Rec("1", GOAL, status="cancelled", ok=False),      # V2-196: the operator stopped it; he knows
    _Rec("1", GOAL, status="done", ok=True),            # it worked
])
def test_nothing_is_pushed_for_a_death_that_did_not_happen(rec):
    d._remember_ended(rec)
    assert brain_notes.drain() == []


def test_the_status_line_SURVIVES_for_a_real_death():
    """The rendered block is not removed: it is the context of the next five minutes, and it is now true. What
    changed is that the ORDER travels by the path that reaches the turn."""
    d._remember_ended(_Rec("1", GOAL))
    rows = d.recently_ended_sessions()
    assert len(rows) == 1 and rows[0]["ok"] is False


def test_the_resume_decision_is_taken_ONCE_and_shared():
    """The guard is only worth anything if the death filing reads a predicate DERIVED from the one that actually
    relaunches the task. Asserted on the source: two independent copies of that condition would drift, and the
    drift is invisible — one of them files a death while the other quietly retries.

    V2-238 SPLIT the predicate in two, on purpose, because there turned out to be two ways for the errand to
    carry on and only one of them relaunches here: `_will_resume` (V2-049 auto-resume, which this function
    fires) and `_handoff` (`_finish` already relaunched — relaying it again would put TWO workers on one
    errand). The guard survives the split by keeping the derivation single: `_continues` is defined from
    `_will_resume`, never re-derived, and the death filing reads it."""
    import inspect
    src = inspect.getsource(d._run_session)
    assert src.count("_will_resume = bool(") == 1
    assert src.count("_continues = bool(") == 1
    assert "_continues = bool(_will_resume or _handoff)" in src
    assert "_remember_ended(rec, resuming=_continues)" in src
    assert "if _will_resume:\n                _schedule_auto_resume(req)" in src
