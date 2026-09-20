"""Node 3.64 — the turn asks Jev ONCE, on the ADMITTED sentence, and never blocks on it.

Measured 2026-09-20: Jev's cost is the ROUND TRIP, not the questions — 1 question 800 ms, 4
heterogeneous 708-826 ms, 100 candidates 1041 ms — and the engine was making two trips per turn for
two questions, with two more callers opening their own BLOCKING socket from inside the voice
provider's `async def` (up to 900 ms of frozen event loop, shared with STT, TTS and barge-in).

So: one brief, fired when the turn is ADMITTED, carrying every question that is read AFTER the model
answers; and the readers `peek` it instead of calling. What this file pins is the half that keeps
being assumed rather than tested — that the wire is reached exactly once, that it is reached with
the sentence the MODEL gets and not a fragment of it, that the state the questions carry is true,
and that nobody waits.

V2-726 A2 added the last three. The first version of this file proved «one trip» while the brief was
still fired before echo suppression and before the accumulator, and while the filler opened a second
socket a second later — so «one trip» was true of the code under test and false of the turn.
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
    assert asked == {tb.CANVAS_KEY, tb.REQUEST_KEY, tb.ESCALATE_KEY, tb.TARGET_KEY}, asked


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
    assert set(wire.calls[0]["questions"]) == {tb.CANVAS_KEY, tb.REQUEST_KEY, tb.ESCALATE_KEY}


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


# ── A2 · the sentence it judges is the sentence the model gets ───────────────────────────────────
def test_the_filler_question_travels_in_the_SAME_brief(wire):
    """A2's headline number: 2 trips → 1. The cover's class used to be its own socket.

    `filler_audio.arm` fired `jev.request_async` about one second after the brief, over the same
    words, for a verdict read at the same deadline. Nothing about it was pre-model: the cover sounds
    ~1.1 s in, which is after the brief lands. It is a question, so it belongs in the question set.
    """
    _settle(tb.ask("ponme música de los ochenta", open_ids=["musica"]))
    assert len(wire.calls) == 1
    assert tb.REQUEST_KEY in wire.calls[0]["questions"], "the filler's question is not in the brief"
    crit = wire.calls[0]["questions"][tb.REQUEST_KEY]["criteria"]
    assert set(crit) == set(jev.REQUEST_TYPES), "the request-type options drifted from jev.REQUEST_TYPES"


def test_the_previous_reply_rides_in_its_OWN_question(wire):
    """«enduro» after we asked «¿enduro o cross?» is an ANSWER, not an order — and that verdict is
    the only thing the previous reply is for. A brief has ONE shared state and N instruction blocks,
    so a fact belonging to one question must travel inside it or it colours the others."""
    _settle(tb.ask("enduro", open_ids=[], last_reply="¿la prefieres de enduro o de cross?"))
    qs = wire.calls[0]["questions"]
    assert "enduro o de cross" in qs[tb.REQUEST_KEY]["instructions"]
    assert "enduro o de cross" not in qs[tb.ESCALATE_KEY]["instructions"], (
        "the previous reply leaked into the escalate question, which judges a different thing")
    assert "enduro o de cross" not in wire.calls[0]["state"], "it must not sit in the shared state"


def test_the_escalate_question_carries_the_TRUE_worker_state(wire, monkeypatch):
    """Audit finding 2. `ask_for_turn` never passed these, so the question said «Workers active now:
    no. A worker is waiting for the operator's answer: no» on every turn — including the turns where
    one WAS waiting, which is exactly the shape that must not become a second worker."""
    import nucleo.dispatch as dispatch
    import nucleo.worker_api as wapi
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(wapi, "has_pending_ask", lambda: True)
    _settle(tb.ask_for_turn("enduro"))
    ins = wire.calls[0]["questions"][tb.ESCALATE_KEY]["instructions"]
    assert "Workers active now: yes" in ins
    assert "waiting for the operator's answer: yes" in ins


def test_unknown_worker_state_reads_as_no_and_never_raises(wire, monkeypatch):
    """Fail-soft direction: «no» is the answer that keeps the commission, and escalating is the safe
    side of this gate («a missed errand is worse than a wasted question»)."""
    import nucleo.dispatch as dispatch
    def _boom():
        raise RuntimeError("dispatch is not up")
    monkeypatch.setattr(dispatch, "has_active", _boom)
    _settle(tb.ask_for_turn("búscame vuelos a Tokio"))
    assert "Workers active now: no" in wire.calls[0]["questions"][tb.ESCALATE_KEY]["instructions"]


# ── A2 · a verdict cannot outlive what it was about ──────────────────────────────────────────────
def test_a_verdict_about_a_card_that_CLOSED_is_not_a_repair(wire, monkeypatch):
    """The brief enumerates what is open at fire time; the reader acts 2-4 s later. In between the
    operator can close the card — and then the verdict names something that is not on screen."""
    declared = list((fe.declared_actions("musica") or {}))
    wire.answers[tb.TARGET_KEY] = (f"musica:{declared[0]}", 0.95)
    h = _settle(tb.ask("dale al play", open_ids=["musica"]))
    assert fe.repair_action_from_brief("musica", h) == declared[0], "still open: the repair stands"

    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": ["agenda"]})
    assert fe.repair_action_from_brief("musica", h) is None, (
        "a verdict about a card that is no longer open was used as a repair")


def test_the_brief_says_which_turn_it_belongs_to(wire):
    """Without a turn id, same-turn attribution is temporal rather than a join — which is all the
    audit could say about two events in a real session. A6a builds its events on this stamp."""
    h = _settle(tb.ask("dale al play", open_ids=["musica"], turn_id="turn-7"))
    assert h["turn_id"] == "turn-7"
    assert h["open_ids"] == ["musica"]


# ── A2 · finding 9: the voice channel can never reach the blocking door ──────────────────────────
def test_a_voice_turn_without_a_brief_does_NOT_open_a_blocking_call(wire, monkeypatch):
    """Audit finding 9. `resolve_undeclared_action(brief=None)` falls through to `repair_action`,
    which is a synchronous `urlopen` — and the voice provider calls it from inside its `async def`.

    The hole only opens when the brief failed to build while Jev is still enabled, which is why the
    static ratchet never saw it: the provider names no blocking function, it names the one that
    contains it. `blocking_ok=False` is the voice channel saying it cannot afford to wait.

    ⚠️ It watches `_post_question`, the SINGLE-question transport, and that is the whole test. The
    first version asserted on `wire.calls` — the brief's transport — and stayed GREEN when the guard
    was deleted, because the blocking call goes out the other door and merely FAILED (no network in
    a unit test) instead of being blocked. A disarm that stays green accuses the test.
    """
    blocking: list = []
    monkeypatch.setattr(jev, "_post_question",
                        lambda *a, **k: blocking.append(a) or {"answers": {}})
    kind, val = fe.resolve_undeclared_action(
        "musica", "una_accion_inventada", "dale al play", brief=None, blocking_ok=False)
    assert (kind, val) == ("escalate", None)
    assert blocking == [], (
        "the voice path reached `repair_action`'s synchronous urlopen with no brief to read — "
        "from inside the provider's `async def` that is a frozen event loop (V2-726 A2, finding 9)")
    assert wire.calls == [], "and it did not go through the brief transport either"


def test_the_probe_channel_KEEPS_its_blocking_fallback(wire, monkeypatch):
    """The other half: `blocking_ok` defaults to True because the probe/text channel has no brief
    and no event loop to freeze. Removing the fallback outright would silently downgrade it.

    It fakes the SINGLE-question transport, which is the door `repair_action` uses — proof in itself
    that the two channels take different paths to the same verdict.
    """
    declared = list((fe.declared_actions("musica") or {}))
    single: list = []

    def _one(answer_key, state, instructions, criteria, timeout_s):
        single.append(answer_key)
        return {"answers": {answer_key: {"choice": declared[0], "confidence": 0.95,
                                         "probabilities": {declared[0]: 0.95}}}}

    monkeypatch.setattr(jev, "_post_question", _one)
    kind, val = fe.resolve_undeclared_action("musica", "una_accion_inventada", "dale al play")
    assert kind == "repair" and val == declared[0]
    assert single == ["widget_action"], "the probe channel must still be able to ask"
    assert wire.calls == [], "and it does not go through the brief transport"
