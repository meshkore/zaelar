"""Node 3.64 — the turn asks Jev ONCE, and the voice path never blocks on it (V2-726 F1+F2).

Measured 2026-09-20: Jev's cost is the ROUND TRIP, not the questions — 1 question 800 ms, 4
heterogeneous 708-826 ms, 100 candidates 1041 ms — and the engine was making two trips per turn for
two questions, with two more callers opening their own BLOCKING socket from inside the voice
provider's `async def` (up to 900 ms of frozen event loop, shared with STT, TTS and barge-in).

So: one brief, fired when the turn starts, carrying every question that is read AFTER the model
answers; and the readers `peek` it instead of calling. What this file pins is the half that keeps
being assumed rather than tested — that the wire is reached exactly once, and that nobody waits.
"""
from __future__ import annotations

import pytest

from nucleo import jev
from nucleo.flash import escalation_guard as eg
from nucleo.flash import frontend as fe
from nucleo.flash import turn_brief as tb


@pytest.fixture
def wire(monkeypatch):
    """Jev ON with the socket replaced. `wire.calls` is what most of these tests assert."""
    monkeypatch.setattr(jev, "_read_key", lambda: "k-for-tests")
    monkeypatch.delenv("ZAELAR_JEV", raising=False)

    class _Wire:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.answers: dict[str, tuple[str, float]] = {}   # key -> (choice, confidence)

        def __call__(self, state, questions, timeout_s):
            self.calls.append({"state": state, "questions": questions})
            out = {}
            for key, q in questions.items():
                choice, conf = self.answers.get(key, (next(iter(q["criteria"])), 0.95))
                out[key] = {"choice": choice, "confidence": conf, "probabilities": {choice: conf}}
            return {"answers": out}

    w = _Wire()
    monkeypatch.setattr(jev, "_post_many", w)
    return w


def _settle(handle, t=2.0):
    if handle and handle.get("event"):
        handle["event"].wait(t)
    return handle


# ── one trip ─────────────────────────────────────────────────────────────────────────────────────
def test_the_whole_brief_is_one_call(wire):
    """THE point of F1, and the metric: the canvas verb and the escalate pair were TWO sockets and
    two threads on every turn, and the route would have opened a third. One trip now carries all of
    them — measured, N questions cost what one costs."""
    _settle(tb.ask("dale al play", open_ids=["musica", "results"]))
    assert len(wire.calls) == 1, f"the brief made {len(wire.calls)} trips, not one"
    asked = set(wire.calls[0]["questions"])
    assert asked == {tb.CANVAS_KEY, tb.ESCALATE_KEY, tb.TARGET_KEY}, asked


def test_the_canvas_verb_travels_in_the_brief_and_reads_the_same(wire):
    """Folding it in may not change what it ANSWERS — both channels share `resolve_canvas_verb`."""
    from nucleo.flash import show_target as st
    wire.answers[tb.CANVAS_KEY] = ("close", 0.98)
    h = _settle(tb.ask("cierra todo", open_ids=[]))
    assert st.resolve_canvas_verb(h)[0] == "close"
    assert len(wire.calls) == 1, "the canvas verb must not open its own trip any more"
    wire.answers[tb.CANVAS_KEY] = ("close", 0.2)
    h2 = _settle(tb.ask("cierra todo", open_ids=[]))
    assert st.resolve_canvas_verb(h2)[0] == "neither", "an unsure verb is still today's path"


def test_the_questions_are_enumerated_from_DECLARED_actions(wire):
    """Initiative rule 2, proved rather than trusted: the options are manifest actions of what is
    OPEN, keyed `widget:action`, plus `none`. Never free text, never a table of ours."""
    _settle(tb.ask("dale al play", open_ids=["musica"]))
    crit = wire.calls[0]["questions"][tb.TARGET_KEY]["criteria"]
    declared = fe.declared_actions("musica") or {}
    assert declared, "the fixture needs a widget that declares actions"
    assert "none" in crit
    assert {k.split(":", 1)[1] for k in crit if k != "none"} <= set(declared)
    assert all(k == "none" or k.startswith("musica:") for k in crit)


def test_nothing_open_asks_nothing_about_the_screen(wire):
    """A question with no candidates is not asked — an empty enumeration is a coin flip."""
    _settle(tb.ask("¿qué hora es?", open_ids=[]))
    assert set(wire.calls[0]["questions"]) == {tb.CANVAS_KEY, tb.ESCALATE_KEY}


def test_an_empty_turn_asks_nothing_at_all(wire):
    assert tb.ask("   ") is None
    assert wire.calls == []


# ── the readers, and that they never wait ────────────────────────────────────────────────────────
def test_the_escalate_gate_reads_the_brief(wire):
    wire.answers[tb.ESCALATE_KEY] = ("handle_inline", 0.9)
    h = _settle(tb.ask("¿qué hora es?", open_ids=[]))
    assert eg.judge_escalation_from_brief(h) == "handle_inline"
    assert len(wire.calls) == 1, "reading must not make a second trip"


def test_an_unsure_escalate_keeps_todays_path(wire):
    wire.answers[tb.ESCALATE_KEY] = ("handle_inline", 0.3)
    h = _settle(tb.ask("búscame vuelos a Tokio", open_ids=[]))
    assert eg.judge_escalation_from_brief(h) == "escalate"


def test_a_brief_still_in_flight_is_todays_path_and_is_not_waited_for():
    """`peek`, never `wait`. 56 of 87 real directed turns died to barge-in before they finished —
    a reader that blocked would be paying for turns that no longer exist."""
    import threading
    flying = {"event": threading.Event(), "result": None}     # never set
    assert eg.judge_escalation_from_brief(flying) == "escalate"
    assert fe.repair_action_from_brief("musica", flying) is None


def test_no_brief_at_all_is_todays_path():
    assert eg.judge_escalation_from_brief(None) == "escalate"
    assert fe.repair_action_from_brief("musica", None) is None


def test_the_action_repair_reads_the_brief(wire):
    declared = list((fe.declared_actions("musica") or {}))
    wire.answers[tb.TARGET_KEY] = (f"musica:{declared[0]}", 0.95)
    h = _settle(tb.ask("dale al play", open_ids=["musica"]))
    assert fe.repair_action_from_brief("musica", h) == declared[0]
    assert len(wire.calls) == 1


def test_a_verdict_about_another_card_is_not_a_repair_for_this_one(wire):
    """The brief answers for the WHOLE screen; a repair is only the part addressed to THIS widget.

    Measured against two cards that SHARE the action name, which is the only case where the owner
    check is load-bearing: `musica` and `youtube` both declare play/pause/next/volume_down. The
    first version of this test used `results`, which declares none of them — so it passed with the
    owner check deleted, because the declared-actions filter caught it anyway. A disarm that stays
    green accuses the test.
    """
    shared = sorted(set(fe.declared_actions("musica") or {}) & set(fe.declared_actions("youtube") or {}))
    assert shared, "this test needs two open widgets that declare the same action name"
    act = shared[0]
    wire.answers[tb.TARGET_KEY] = (f"musica:{act}", 0.95)
    h = _settle(tb.ask("dale al play", open_ids=["musica", "youtube"]))
    assert fe.repair_action_from_brief("musica", h) == act, "the addressed card gets its repair"
    assert fe.repair_action_from_brief("youtube", h) is None, (
        f"«musica:{act}» was read as a repair for youtube, which declares `{act}` too — the verdict "
        f"names its own card and that is the whole disambiguation")


def test_none_is_not_a_repair(wire):
    wire.answers[tb.TARGET_KEY] = ("none", 0.99)
    h = _settle(tb.ask("¿qué hora es?", open_ids=["musica"]))
    assert fe.repair_action_from_brief("musica", h) is None


# ── parity: off, failed, oversized ───────────────────────────────────────────────────────────────
def test_switched_off_asks_nothing(wire, monkeypatch):
    monkeypatch.setenv("ZAELAR_JEV", "0")
    assert tb.ask("dale al play", open_ids=["musica"]) is None
    assert wire.calls == []


def test_a_failed_call_is_todays_path(wire, monkeypatch):
    def _boom(*a, **k):
        raise OSError("network is down")
    monkeypatch.setattr(jev, "_post_many", _boom)
    h = _settle(tb.ask("dale al play", open_ids=["musica"]))
    assert eg.judge_escalation_from_brief(h) == "escalate"
    assert fe.repair_action_from_brief("musica", h) is None


def test_an_oversized_brief_is_refused_before_the_wire(wire):
    """A caller that enumerates a database would turn one cheap classifier into a slow expensive
    one, and the failure would look like a truncated verdict rather than an error."""
    huge = {f"q{i}": {"instructions": "x", "criteria": {"a": "a", "b": "b"}}
            for i in range(jev.MAX_QUESTIONS + 1)}
    with pytest.raises(jev.JevBriefTooBig):
        jev.choose_many_sync("hola", huge)
    with pytest.raises(jev.JevBriefTooBig):
        jev.choose_many_sync("x" * (jev.MAX_STATE_CHARS + 1),
                             {"q": {"instructions": "x", "criteria": {"a": "a"}}})
    assert wire.calls == [], "nothing oversized may reach the wire"
