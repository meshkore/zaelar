"""V2-224 — «did I already tell it?» was a deduction made by the model, and it had to be a fact supplied by us.

V2-221 added the unconditional instruction («TELL IT THIS TURN») and it worked: the harness measured 2 out of 2 turns
saying it, on turn 2, without anyone asking. But it put the anti-repetition rule INSIDE the same sentence
—«if you already told it in an earlier turn, do not repeat it»— and this was measured in TWO rounds of the SAME commit with
opposite results:

    round 5 → it said it on turn 2 and REPETED it on 5, 6, 7, 8, and 9.            (the V2-189 broken record)
    round 6 → it said it on turn 2 and then DENIED it for seven turns: «I am still working on it»,
              «Give me a moment», «I am relaunching it now».

Same commit, same clause, opposite failures. That is not a wrongly set threshold: it is that the «already told it»
record did not govern the decision. In one round it did not find it and repeated it; in the other it found it and fell
completely SILENT — and silencing the repetition is not silencing the state.

We know how many turns have carried that ending forward. So it is counted, and each turn receives ONE
instruction: the first time, say it; from then on, do not repeat it BUT keep it dead, and the reassuring phrases
remain forbidden.
"""
import pytest

from nucleo import dispatch as d


class _Rec:
    def __init__(self, tid, goal, status="error", ok=False, summary=""):
        self.task_id, self.goal, self.status, self.ok, self.result_summary = tid, goal, status, ok, summary


@pytest.fixture(autouse=True)
def _clean():
    e = dict(d._ENDED_SESSIONS)
    d._ENDED_SESSIONS.clear()
    yield
    d._ENDED_SESSIONS.clear(); d._ENDED_SESSIONS.update(e)


GOAL = "Busca hoteles de 4 estrellas en Sevilla"


def _state(monkeypatch, rows):
    from nucleo.flash import prompt as P
    monkeypatch.setattr(d, "recently_ended_sessions", lambda: rows, raising=False)
    return P.live_state()


FAILED = [{"id": "1", "goal": GOAL, "status": "error", "ok": False, "summary": "", "ago_s": 5, "told": 0}]


def test_a_fresh_death_starts_at_zero():
    d._remember_ended(_Rec("1", GOAL))
    assert d.recently_ended_sessions()[0]["told"] == 0


def test_the_turn_that_carried_it_marks_it(monkeypatch):
    """The counter is advanced by the turn that carried it forward, not the one that died: there may be no turn
    between the death and the next prompt."""
    d._remember_ended(_Rec("1", GOAL))
    _state(monkeypatch, d.recently_ended_sessions())
    assert d._ENDED_SESSIONS["1"]["told"] == 1


def test_the_FIRST_turn_gets_the_notice(monkeypatch):
    st = _state(monkeypatch, FAILED)
    assert "DÍSELO EN ESTE TURNO" in st


def test_and_the_ONES_AFTER_are_told_not_to_repeat_it(monkeypatch):
    st = _state(monkeypatch, [{**FAILED[0], "told": 1}])
    assert "NO se lo vuelvas a anunciar" in st
    assert "DÍSELO EN ESTE TURNO" not in st


def test_but_the_STATE_survives_the_silence(monkeypatch):
    """What round 6 lost: stopping the announcement is not returning to «I am still working on it». The task remains
    dead and the reassuring phrase remains forbidden."""
    st = _state(monkeypatch, [{**FAILED[0], "told": 3}])
    assert "SIGUE MUERTA" in st
    for banned in ("sigo con ello", "te aviso en cuanto lo tenga", "dame un momento"):
        assert banned in st.lower(), banned


def test_only_ONE_instruction_per_turn(monkeypatch):
    """The root cause: two commands in the same sentence were resolved by a coin toss depending on the round."""
    first = _state(monkeypatch, FAILED)
    later = _state(monkeypatch, [{**FAILED[0], "told": 1}])
    assert ("DÍSELO EN ESTE TURNO" in first) != ("DÍSELO EN ESTE TURNO" in later)
    assert ("NO se lo vuelvas a anunciar" in first) != ("NO se lo vuelvas a anunciar" in later)


def test_a_task_that_ended_WELL_is_never_counted(monkeypatch):
    """Sensitivity: the counter is for DEATHS. Marking a successful ending would spend the first turn of the next one."""
    ok = [{"id": "9", "goal": GOAL, "status": "done", "ok": True, "summary": "hecho", "ago_s": 2, "told": 0}]
    d._ENDED_SESSIONS["9"] = dict(ok[0])
    _state(monkeypatch, ok)
    assert d._ENDED_SESSIONS["9"]["told"] == 0


def test_a_CANCELLED_task_is_never_counted_either(monkeypatch):
    """V2-196: stopping is not failing, and the operator already knows because they stopped it."""
    c = [{"id": "9", "goal": GOAL, "status": "cancelled", "ok": False, "summary": "", "ago_s": 2, "told": 0}]
    d._ENDED_SESSIONS["9"] = dict(c[0])
    _state(monkeypatch, c)
    assert d._ENDED_SESSIONS["9"]["told"] == 0


def test_marking_an_id_that_no_longer_exists_is_harmless():
    """The record expires after 5 minutes; the turn that carried it forward may arrive late."""
    d.mark_death_reported(["no-existe", ""])
