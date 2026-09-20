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


def test_nothing_open_asks_nothing_about_the_SCREEN(wire):
    """A question with no candidates is not asked — an empty enumeration is a coin flip.

    Since A4 the screen question has a twin for exactly this case (`catalog_widget`: which widget of
    the catalogue is being NAMED), so what must be absent is the one about what is ON SCREEN, which
    is nothing. The two are never asked together — see `test_the_two_screen_questions_...`.
    """
    _settle(tb.ask("¿qué hora es?", open_ids=[]))
    assert tb.TARGET_KEY not in wire.calls[0]["questions"]
    assert {tb.CANVAS_KEY, tb.REQUEST_KEY, tb.ESCALATE_KEY} <= set(wire.calls[0]["questions"])


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


# ── A4 · the screen question knows WHICH card, not just which widget ─────────────────────────────
def test_two_cards_of_the_SAME_widget_are_two_candidates(wire):
    """The measurement that decides this design (V2-726 §4-bis, five open cards): «enséñame el
    tercero» came back `youtube:play_result` at 0.70 — confident and WRONG, with the third row
    sitting in an open `results` card. Keying by widget TYPE meant a verdict could not name which of
    two cards it meant, so the only failure mode the plan requires to be zero was structural."""
    _settle(tb.ask("enséñame el tercero", open_ids=["results::t7", "results::t9"]))
    keys = [k for k in wire.calls[0]["questions"][tb.TARGET_KEY]["criteria"] if k != "none"]
    owners = {k.rpartition(":")[0] for k in keys}
    assert owners == {"results::t7", "results::t9"}, owners


def test_a_verdict_names_its_own_instance_and_the_sibling_gets_nothing(wire):
    """Two cards of a kind declare the same actions, so the instance is the whole disambiguation."""
    declared = list((fe.declared_actions("results") or {}))
    assert declared, "this test needs a widget that declares actions"
    act = declared[0]
    wire.answers[tb.TARGET_KEY] = (f"results::t7:{act}", 0.95)
    h = _settle(tb.ask("enséñame el tercero", open_ids=["results::t7", "results::t9"]))
    assert fe.repair_action_from_brief("results::t7", h) == act
    assert fe.repair_action_from_brief("results::t9", h) is None, (
        "the verdict for one card was read as a repair for its sibling")


def test_each_candidate_carries_what_ITS_card_is_showing(wire, monkeypatch):
    """The live rail. «reproduce» chose `musica` over `youtube` with nothing to justify it — both
    declare `play` and `next`, and the question carried only the list of what was open. What each
    card is SHOWING is the fact that separates them, and only the card can say it."""
    from widgets import instances as inst
    faces = {"musica": {"label": "sonando: Bohemian Rhapsody"},
             "youtube": {"label": "pausado: receta de paella"}}
    monkeypatch.setattr(inst, "card_face", lambda wid: faces.get(wid, {}))
    _settle(tb.ask("siguiente", open_ids=["musica", "youtube"]))
    crit = wire.calls[0]["questions"][tb.TARGET_KEY]["criteria"]
    blob = " ".join(crit.values())
    assert "sonando: Bohemian Rhapsody" in blob and "pausado: receta de paella" in blob, (
        "the question cannot tell the two cards apart: it carries no live state for either")


def test_a_card_that_cannot_describe_itself_still_gets_its_candidates(wire, monkeypatch):
    """Refines DOWNWARDS only. A widget with no `card_face` (or one that raises) must not vanish
    from its own screen — the fallback is the id, which is exactly what the question carried
    before A4: never worse, often better."""
    from widgets import instances as inst

    def _boom(wid):
        raise RuntimeError("this widget cannot describe itself")
    monkeypatch.setattr(inst, "card_face", _boom)
    _settle(tb.ask("dale al play", open_ids=["musica"]))
    keys = [k for k in wire.calls[0]["questions"][tb.TARGET_KEY]["criteria"] if k != "none"]
    assert keys and all(k.startswith("musica:") for k in keys)


def test_an_action_that_needs_a_row_is_not_offered_when_there_are_no_rows(wire, monkeypatch):
    """«Play the third one» on an empty list is not a capability the operator lacks — it is a target
    that does not exist, and offering it is how a chooser becomes confidently wrong. Fewer and more
    pertinent candidates is also what brings the measured 15 KB of criteria down."""
    from widgets import refs
    declared = list((fe.declared_actions("results") or {}))
    needs_row = [a for a in declared if refs.id_field_for_action("results", a)]
    assert needs_row, "this test needs an action that names an EXISTING row"
    act = needs_row[0]

    field = refs.id_field_for_action("results", act)
    monkeypatch.setattr(refs, "_exposes_ref_index", lambda wid: True)

    # BASELINE, and it is half the test: with a row present the action IS offered. Without it, the
    # assertion below would hold for an action that is simply never offered at all.
    monkeypatch.setattr(refs, "_ref_index",
                        lambda wid: [{"id": "r1", "label": "una fila", "field": field}])
    _settle(tb.ask("abre el tercero", open_ids=["results"]))
    assert f"results:{act}" in wire.calls[0]["questions"][tb.TARGET_KEY]["criteria"], (
        f"«{act}» is not offered even with rows present — this test would prove nothing")

    wire.calls.clear()
    monkeypatch.setattr(refs, "_ref_index", lambda wid: [])
    _settle(tb.ask("abre el tercero", open_ids=["results"]))
    keys = list(wire.calls[0]["questions"][tb.TARGET_KEY]["criteria"])
    assert f"results:{act}" not in keys, "an action with nothing to act on was offered as a target"
    assert len(keys) > 1, "the whole card vanished instead of one impossible action"


def test_an_action_that_CREATES_something_is_always_possible(wire, monkeypatch):
    """The defect the first version of the filter shipped, caught by a test that picked the first
    declared action and found it gone. `contract.selector_for` answers «which key identifies this
    call» — for `create_playlist` that is `name`, the name of a list that does not exist YET. Asking
    it here deleted every creation action from an empty widget: «crea una lista Rock» had nothing to
    be aimed at. The right question is `refs.id_field_for_action`: which key names an EXISTING row."""
    from widgets import refs
    monkeypatch.setattr(refs, "_ref_index", lambda wid: [])
    monkeypatch.setattr(refs, "_exposes_ref_index", lambda wid: True)
    _settle(tb.ask("crea una lista que se llame Rock", open_ids=["musica"]))
    keys = list(wire.calls[0]["questions"][tb.TARGET_KEY]["criteria"])
    assert "musica:create_playlist" in keys, (
        "a creation action was filtered out because the widget has no rows yet")


def test_a_verdict_about_an_instance_that_closed_is_stale(wire, monkeypatch):
    """A sibling staying open does not save it: the card he was looking at is gone, and the other
    one is a different card with different rows."""
    declared = list((fe.declared_actions("results") or {}))
    wire.answers[tb.TARGET_KEY] = (f"results::t7:{declared[0]}", 0.95)
    h = _settle(tb.ask("enséñame el tercero", open_ids=["results::t7", "results::t9"]))
    from memory import api as memapi
    monkeypatch.setattr(memapi, "state", lambda: {"open_widgets": ["results::t9"]})
    assert fe.repair_action_from_brief("results::t7", h) is None


# ── A4 · with nothing open, the question is WHICH WIDGET — asked with the words he uses ──────────
def test_nothing_open_asks_which_widget_of_the_catalogue(wire):
    _settle(tb.ask("ábreme el vídeo", open_ids=[]))
    asked = set(wire.calls[0]["questions"])
    assert tb.CATALOG_KEY in asked and tb.TARGET_KEY not in asked


def test_the_two_screen_questions_are_never_asked_together(wire):
    """With cards open the ACTION is what disambiguates (0.94 vs 0.26 measured); asking both would
    put two answers about the same order in one brief, and nothing decides between them."""
    _settle(tb.ask("dale al play", open_ids=["musica"]))
    asked = set(wire.calls[0]["questions"])
    assert tb.TARGET_KEY in asked and tb.CATALOG_KEY not in asked


def test_the_catalogue_question_carries_the_words_he_CALLS_them(wire):
    """V2-726 §4-bis: criteria from the `desc` alone got 6/9; «Name» + the same desc got 8/9. The
    alias table (V2-082) already existed and was never handed to the chooser — which is why the
    operator's own example «ábreme el vídeo» answered `none` at 0.52-0.61, confidently wrong, when
    the word «vídeo» is declared right there in YouTube's aliases."""
    _settle(tb.ask("ábreme el vídeo", open_ids=[]))
    crit = wire.calls[0]["questions"][tb.CATALOG_KEY]["criteria"]
    assert "youtube" in crit and "none" in crit
    assert "«YouTube»" in crit["youtube"], "the widget's NAME is not in its own criterion"
    # An alias the DESCRIPTION does not contain, or this proves nothing: YouTube's own prose says
    # «reproduce el vídeo de verdad», so asserting on «vídeo» alone stayed green with the alias list
    # deleted. A disarm that stays green accuses the test.
    import json as _json
    import pathlib as _pathlib
    man = _json.loads((_pathlib.Path(__file__).resolve().parents[3] / "widgets" / "youtube"
                       / "manifest.json").read_text(encoding="utf-8"))
    desc = str(man.get("description") or "").lower()
    only_alias = next((a for a in (man.get("aliases") or []) if a.lower() not in desc), "")
    assert only_alias, "YouTube declares no alias that is absent from its description"
    assert only_alias.lower() in crit["youtube"].lower(), (
        f"«{only_alias}» is in YouTube's declared aliases and did not reach the question — the "
        f"alias table is the product surface of this decision (V2-726 §4-bis)")


def test_an_oversized_catalogue_is_retrieval_not_a_bigger_question(wire, monkeypatch):
    """INI-027 §7, the operator's own rule: an index narrows, a model chooses. Past the cap the
    answer is not a longer enumeration — so the question is simply not asked, and the turn keeps
    exactly what it does today."""
    from widgets import runtime
    monkeypatch.setattr(runtime, "catalog",
                        lambda: [{"id": f"w{i}", "name": f"W{i}"}
                                 for i in range(tb.MAX_CATALOG_CANDIDATES + 1)])
    assert tb.catalog_question() is None
    _settle(tb.ask("ábreme el vídeo", open_ids=[]))
    assert tb.CATALOG_KEY not in wire.calls[0]["questions"]
