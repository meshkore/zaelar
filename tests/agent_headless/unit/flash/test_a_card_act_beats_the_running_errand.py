"""A turn a CARD owns never steers nor stops the errand running behind it (V2-831 T-19 R7+R8, the V2-747 class).

Demo sandbox pass, 2026-10-29, with music playing and a price-monitor errand running:

  · U2 «no, put like a prayer» — `corrects_last` read his words as a correction of the LAST act (a music play), and
    the steer verdict sent the same sentence to the monitor worker as «new instructions from the operator».
  · U3 «pause it a sec» — `screen_action` read the music card's pause at 1.00, and the stop backstop, reading
    `stop_errand = stop`, killed the monitor errand mid price-check.

One rule, `stop.card_owns_the_turn`, is read by both the steer and the stop backstop: a sure act on a card, a
card or lane that carried the words out, or a sure correction of the last act (a card's) means the errand is not
the target. A stop or steer addressed to the errand, with no card act in the turn, still reaches it.
"""
from __future__ import annotations

import asyncio
import itertools
import threading
import time
from types import SimpleNamespace

import pytest

from nucleo import done_ops
from nucleo.request import stop as sd
from voice import trace

_SEQ = itertools.count(1)


def _turn(origin: str = "turno", ago: float = 0.0) -> str:
    """A trace born as HIS turn (`turno`) or another stimulus, without emitting its root event."""
    tid = f"Tr78-{next(_SEQ)}"
    trace._BORN[tid] = (origin, time.time() - ago)
    return tid


def _note(*op, tid: str | None = None, span: str = ""):
    """A card op written inside a turn: his (the default), or an errand worker's (`span="worker:9"`)."""
    with trace.scope(_turn() if tid is None else tid, span):
        done_ops.note(*op)

#: His correction of the last act (a card's), in two languages and two card domains.
CORRECTIONS = [
    ("no, put like a prayer", ("musica", "play", {"query": "Hung Up"})),
    ("no, pon la de Like a Prayer", ("musica", "play", {"query": "Hung Up"})),
    ("no, a las cinco, no a las cuatro", ("agenda", "move_meeting", {"start": "16:00"})),
    ("no, the second picture, not the first", ("imagenes", "set_wallpaper", {"index": 1})),
]
#: A pause of the card, read sure, with a stop reading of the errand beside it.
PAUSES = [("pause it a sec", "musica:pause"), ("páralo un momento", "musica:pause"),
          ("hold the video there", "youtube:pause")]
#: A real stop / steer addressed to the errand, with no card act in the turn.
REAL_STOPS = ["stop the price check", "para lo de los precios", "cancela la búsqueda de vuelos"]
REAL_STEERS = ["look on Amazon too, not only eBay", "mira también en Amazon, no solo en eBay"]


def _brief(**verdicts):
    """A READY brief: each kwarg `key=(choice, confidence)`."""
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-r78", "open_ids": [],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in verdicts.items()}}


@pytest.fixture
def errand(monkeypatch):
    """One live errand «9» (the price monitor); records what was cancelled and injected. A clean done_ops ring."""
    from nucleo import dispatch
    seen = {"cancelled": [], "injected": []}
    rec = SimpleNamespace(goal="Monitor the price of the Sony headphones", waiting_on="", started=time.time() - 300,
                          injects=[], trace_id=_turn(ago=300))   # HE commissioned it five minutes ago
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: ["9"])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec if str(tid) == "9" else None)
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: seen["cancelled"].append(w) or ["9"])
    monkeypatch.setattr(dispatch, "inject_soon", lambda w, m: seen["injected"].append((w, m)))
    seen["rec"] = rec
    done_ops.reset()
    yield seen
    done_ops.reset()


# ── R7 · a correction of the last card act stays the card's ─────────────────────────────────────────────────
@pytest.mark.parametrize("text,last", CORRECTIONS)
def test_a_correction_of_the_last_card_act_is_never_steered_to_the_errand(text, last, errand):
    _note(*last)
    acted = {"v": None}
    brief = _brief(stop_errand=("steer", 0.95), corrects_last=("corrects_last", 0.95),
                   errand_target=("running_errand", 0.9))
    assert sd.steer(brief, text, worker_acted=acted) == ""
    assert errand["injected"] == [], "his correction of the card reached the errand"
    assert acted["v"] is None, "an unrelayed correction must not mark the turn as acted (`inject`)"


@pytest.mark.parametrize("text,last", CORRECTIONS[:2])
def test_a_correction_of_the_last_card_act_leaves_the_turn_to_its_repair_passes(text, last, errand, monkeypatch):
    """The voice act completion: the turn keeps `_no_tool` True and `worker_acted` unset, so the promise-repair
    passes (another door) still see a turn that did nothing — the errand never swallows it as `inject`."""
    _note(*last)
    out, worker_acted, _ops = _complete(text, _brief(stop_errand=("steer", 0.95),
                                                     corrects_last=("corrects_last", 0.95)), monkeypatch)
    assert errand["injected"] == []
    assert worker_acted["v"] is None and out.get("_no_tool") is True


# ── R7b · a correction belongs to whoever ACTED LAST (pass 2: corrects_last mid-confidence, steer 0.84) ────────
#: U2 as pass 2 read it: no card verdict (screen_action none 0.50), a steer below the veto floor, a correction read
#: at mid confidence. The FACT — the last act was the music card's — decides with it.
def _u2_brief(corrects: float = 0.7):
    return _brief(stop_errand=("steer", 0.84), errand_target=("running_errand", 0.84), screen_action=("none", 0.5),
                  corrects_last=("corrects_last", corrects))


@pytest.mark.parametrize("text", [CORRECTIONS[0][0], CORRECTIONS[1][0]])
def test_a_mid_confidence_correction_after_a_card_act_is_the_cards(text, errand):
    _note("musica", "play", {"query": "Hung Up"})
    acted = {"v": None}
    assert sd.last_act_owner() == "card"
    assert sd.steer(_u2_brief(), text, worker_acted=acted) == "" and acted["v"] is None
    assert errand["injected"] == []


@pytest.mark.parametrize("text", REAL_STEERS)
def test_a_correction_after_the_errand_acted_last_is_the_errands(text, errand):
    """He played music, then corrected the errand (an injection, newer): «no, …» now corrects the errand."""
    _note("musica", "play", {"query": "Hung Up"})
    time.sleep(0.01)
    errand["rec"].injects.append(SimpleNamespace(text="only under 200 euros", ts=time.time(), trace=_turn()))
    assert sd.last_act_owner() == "errand"
    assert sd.steer(_u2_brief(0.95), text, worker_acted={"v": None}) == "9"


def test_a_mid_confidence_correction_never_decides_alone(errand):
    """No card act behind it: the same mid-confidence reading leaves the steer to the errand."""
    assert sd.last_act_owner() == "errand"
    assert sd.steer(_u2_brief(), REAL_STEERS[0], worker_acted={"v": None}) == "9"


def test_a_correction_below_the_licence_is_no_correction(errand):
    _note("musica", "play", {"query": "x"})
    assert sd.steer(_u2_brief(0.3), REAL_STEERS[0], worker_acted={"v": None}) == "9"


def test_nobody_acted_means_no_owner(monkeypatch):
    from nucleo import dispatch
    done_ops.reset()
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: [])
    assert sd.last_act_owner() == ""


@pytest.mark.parametrize("text", [CORRECTIONS[0][0], CORRECTIONS[1][0]])
def test_through_the_turn_the_correction_reaches_the_card_and_not_the_errand(text, errand, monkeypatch):
    """The voice act chain (`complete_the_acts`) over pass 2's U2: the model said «— that one instead, right away»
    and called nothing. The steer leaves the turn unmarked, so the promise repair runs the card's call."""
    _note("musica", "play", {"query": "Hung Up"})
    from nucleo.flash import card_commission
    monkeypatch.setattr(card_commission, "named_or_catalogue", lambda brief, text, **k: "musica")

    async def _play(*a, **k):
        return {"widget_id": "musica", "action": "play", "payload": {"query": "Like a Prayer"}}
    out, worker_acted, ops = _complete(text, _u2_brief(), monkeypatch, repair=_play, say="— that one instead, right away.")
    assert errand["injected"] == [], "his correction of the music went to the errand"
    assert worker_acted["v"] is None
    assert ops == [("musica", "play")], f"the promise repair did not run the card's call: {ops}"


def test_a_correction_with_no_card_act_behind_it_steers(errand):
    """Nothing in the funnel's ledger: the correction cannot be about a card's act — the errand's reading stands."""
    brief = _brief(stop_errand=("steer", 0.95), corrects_last=("corrects_last", 0.95))
    assert sd.steer(brief, REAL_STEERS[1], worker_acted={"v": None}) == "9"


@pytest.mark.parametrize("text", REAL_STEERS)
@pytest.mark.parametrize("redo", [None, ("new_request", 0.95), ("unrelated", 0.99)])
def test_a_real_correction_of_the_errand_still_steers_it(text, redo, errand):
    _note("musica", "play", {"query": "x"})        # music played earlier: not what he is correcting
    kw = {"corrects_last": redo} if redo else {}
    acted = {"v": None}
    assert sd.steer(_brief(stop_errand=("steer", 0.95), **kw), text, worker_acted=acted) == "9"
    assert errand["injected"] == [("9", text)] and acted["v"] == "inject"


# ── R7c · only the acts of HIS turns count (pass 3: the monitor's own sheet write made the errand «last») ────────
def _background(errand):
    """What an errand does on its own after U1: its worker writes its sheet (in its span, and over HTTP with no
    trace), the pulse demands a report, and a recheck restarts the record — none of it a turn he spoke."""
    rec = errand["rec"]
    _note("results", "push_items", {"n": 3}, tid=rec.trace_id, span="worker:9")
    _note("results", "push_items", {"n": 1}, tid="")
    rec.injects.append(SimpleNamespace(text="report now", ts=time.time(), trace=""))
    rec.injects.append(SimpleNamespace(text="the goal", ts=time.time(), trace=_turn("cron")))
    rec.started = time.time()


@pytest.mark.parametrize("text", [CORRECTIONS[0][0], CORRECTIONS[1][0]])
def test_an_errands_background_writes_after_his_play_leave_the_card_the_owner(text, errand, monkeypatch):
    _note("musica", "play", {"query": "Hung Up"})          # U1, his turn
    _background(errand)
    assert sd.last_act_owner() == "card"
    from nucleo.flash import card_commission
    monkeypatch.setattr(card_commission, "named_or_catalogue", lambda brief, text, **k: "musica")

    async def _play(*a, **k):
        return {"widget_id": "musica", "action": "play", "payload": {"query": "Like a Prayer"}}
    _out, worker_acted, ops = _complete(text, _u2_brief(), monkeypatch, repair=_play, say="— that one instead.")
    assert errand["injected"] == [] and worker_acted["v"] is None and ops == [("musica", "play")]


@pytest.mark.parametrize("text", ["no, only under 200 euros", "no, solo por debajo de 200 euros"])
def test_a_correction_right_after_he_steered_the_errand_is_the_errands(text, errand, monkeypatch):
    _note("musica", "play", {"query": "Hung Up"})
    time.sleep(0.01)
    errand["rec"].injects.append(SimpleNamespace(text="look on Amazon too", ts=time.time(), trace=_turn()))
    _background(errand)
    assert sd.last_act_owner() == "errand"
    _out, worker_acted, _ops = _complete(text, _u2_brief(0.95), monkeypatch, say="Got it, I'll tell the errand.")
    assert errand["injected"] == [("9", text)] and worker_acted["v"] == "inject"


def test_an_injection_keeps_the_turn_that_sent_it():
    """The record's `Inject` takes the trace of the context that wrote it — HIS turn's for a steer."""
    from nucleo.workers.session_record import Inject
    tid = _turn()
    with trace.scope(tid):
        assert Inject(text="x", ts=0.0).trace == tid
    with trace.scope(""):
        assert Inject(text="y", ts=0.0).trace == ""


def test_inject_soon_carries_his_trace_onto_the_registry_loop(monkeypatch):
    """`inject_soon` crosses to the registry's loop, which copies no context: the injection still runs in his turn."""
    from nucleo import dispatch
    loop, seen, done = asyncio.new_event_loop(), [], threading.Event()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    async def _inject(which, message):
        seen.append(trace.current()); done.set()  # noqa: E702
    monkeypatch.setattr(dispatch, "_LOOP", loop)
    monkeypatch.setattr(dispatch, "inject", _inject)
    tid = _turn()
    try:
        with trace.scope(tid):
            dispatch.inject_soon("9", "look on Amazon too")
        assert done.wait(2.0) and seen == [tid]
    finally:
        loop.call_soon_threadsafe(loop.stop)


# ── R7d · EVERY route that hands his sentence to a running errand asks the same owner rule (pass 5, U2) ────────
#: U2 as pass 5 read it: steer 0.81, screen_action none 0.43 (unsure), corrects_last 0.62, the late catalogue named
#: nobody — and the model said «Switching it to Like a Prayer.» with no act; the promise net relayed it to the monitor.
def _u2_p5():
    return _brief(stop_errand=("steer", 0.81), screen_action=("none", 0.43), corrects_last=("corrects_last", 0.62),
                  canvas=("neither", 0.88), errand_target=("running_errand", 0.6))


@pytest.mark.parametrize("text", [CORRECTIONS[0][0], CORRECTIONS[1][0]])
def test_u2_through_the_turn_the_promise_repair_plays_the_card_it_corrects(text, errand, monkeypatch):
    """The act chain names the card his correction belongs to (the last act of his turns) — the late catalogue is never
    asked — and the promise repair plays it; nothing reaches the monitor."""
    _note("musica", "play", {"query": "Hung Up"})
    _background(errand)
    from nucleo.flash import card_commission
    monkeypatch.setattr(card_commission, "late_catalogue", lambda *a, **k: pytest.fail("the catalogue was asked"))
    asked: list = []

    async def _repair(op_text, reply, widget_id, *a, **k):
        asked.append(widget_id)
        return {"widget_id": widget_id, "action": "play", "payload": {"query": "Like a Prayer"}} if widget_id else None
    _out, worker_acted, ops = _complete(text, _u2_p5(), monkeypatch, repair=_repair, say="Switching it to Like a Prayer.")
    assert asked == ["musica"] and ops == [("musica", "play")]
    assert errand["injected"] == [] and worker_acted["v"] is None


def _in_the_turn(brief, fn):
    """Run `fn` inside one of HIS turns whose brief is `brief` (joinable by trace, as `turn_admit` leaves it)."""
    from nucleo.turn import brief_turn
    with trace.scope(_turn()):
        brief_turn.remember_for_the_turn(brief)
        return fn()


@pytest.mark.parametrize("text", [CORRECTIONS[0][0], CORRECTIONS[1][0]])
def test_the_promise_net_never_relays_a_correction_the_card_owns(text, errand, monkeypatch):
    """The live route of pass 5: `promise_backstop` found «the errand it names» and injected his sentence."""
    _note("musica", "play", {"query": "Hung Up"})
    from nucleo.turn import errands_of_a_turn as _eot
    from voice.engine.llm.providers import promise_backstop
    monkeypatch.setattr(_eot, "promised_refinement", lambda *a, **k: "9")
    out = _in_the_turn(_u2_p5(), lambda: promise_backstop.run(
        "Switching it to Like a Prayer.", did_act=False, op_text=text, prev_pending=[], emit=lambda *a, **k: None,
        escalate=lambda *a, **k: pytest.fail("escalated"), similar_pending=lambda *a: False, brief=_u2_p5()))
    assert errand["injected"] == [] and out != "routed"


def test_the_models_send_to_worker_over_a_turn_the_card_owns_is_refused(errand):
    from nucleo.flash import tool_executor_calls as _calls
    _note("musica", "play", {"query": "Hung Up"})
    acted = {"v": None}
    _in_the_turn(_u2_p5(), lambda: _calls._t_send_to_worker(args={"which": "9", "message": CORRECTIONS[0][0]},
                                                            emit=lambda *a, **k: None, worker_acted=acted))
    assert errand["injected"] == [] and acted["v"] is None


def test_a_turn_that_went_through_the_music_door_owns_its_words(errand):
    from nucleo import consequence
    def _turn_body():
        consequence.passes("music", arg="play")
        from nucleo import dispatch
        return dispatch.relay_his_words("9", "louder")
    assert _in_the_turn(_brief(), _turn_body) is False and errand["injected"] == []


@pytest.mark.parametrize("text", REAL_STEERS)
def test_his_words_for_the_errand_still_reach_it_through_the_door(text, errand):
    """No card owns the turn (he commissioned the monitor, nothing since): the same door relays."""
    acted = {"v": None}
    from nucleo.flash import tool_executor_calls as _calls
    _in_the_turn(_brief(stop_errand=("steer", 0.95)), lambda: _calls._t_send_to_worker(
        args={"which": "9", "message": text}, emit=lambda *a, **k: None, worker_acted=acted))
    assert errand["injected"] == [("9", text)] and acted["v"] == "inject"


# ── R8 · a sure card pause beside a stop reading leaves the errand alive ────────────────────────────────────
@pytest.mark.parametrize("text,action", PAUSES)
def test_a_sure_card_act_beside_a_stop_reading_keeps_the_errand(text, action, errand):
    brief = _brief(stop_errand=("stop", 0.95), screen_action=(action, 1.0), errand_target=("running_errand", 0.9))
    assert sd.repair(brief, text, escalating=False, grammar=lambda: True, acted={},
                     card_acts={"acted": {"widget": False}, "data_done": {"v": None}, "lanes": ()}) == []
    assert errand["cancelled"] == []


@pytest.mark.parametrize("text,action", PAUSES[:2])
def test_the_settle_backstop_keeps_the_errand_under_a_card_act(text, action, errand):
    """The voice stop backstop (`post_stream_settle`): no `🛑 stop worker` over a turn the card owns."""
    worker_acted = {"v": None}
    _settle(text, _brief(stop_errand=("stop", 0.95), screen_action=(action, 1.0)), worker_acted)
    assert errand["cancelled"] == [] and worker_acted["v"] is None


def test_the_settle_backstop_keeps_the_errand_when_the_card_already_acted(errand):
    worker_acted = {"v": None}
    _settle("pause it", _brief(stop_errand=("stop", 0.95)), worker_acted, acted={"widget": True})
    assert errand["cancelled"] == []


@pytest.mark.parametrize("text", REAL_STOPS)
def test_a_real_stop_of_the_errand_still_stops_it(text, errand):
    worker_acted = {"v": None}
    _settle(text, _brief(stop_errand=("stop", 0.95), screen_action=("none", 0.95)), worker_acted)
    assert errand["cancelled"] == [text] and worker_acted["v"] == "stop"


# ── R15 · a replace ends the errand only when SURE, AIMED at it, and no card served the turn (pass 4, M1) ──────
#: M1 «how's apple stock doing today, show me the chart» with the monitor running: stop_errand=replace 0.59,
#: errand_target=none — and the chart answered on screen. A new, unrelated question is a NEW errand.
UNRELATED = ["how's apple stock doing today, show me the chart", "¿cómo van hoy las acciones de Apple? enséñame la gráfica"]
REAL_REPLACES = ["forget the monitors, look for a standing desk instead",
                 "olvida los monitores, búscame un escritorio elevable en su lugar"]


def _m1(confidence: float = 0.59, target: str = "none"):
    return _brief(stop_errand=("replace", confidence), errand_target=(target, 0.9), screen_action=("none", 0.89),
                  canvas=("show", 0.58))


def _the_turn(text, brief, monkeypatch, *, acted=None):
    """The voice turn's two halves a replace crosses: the stop backstop (`settle`) and the close that would start
    its successor (`turn_after.close_the_turn`). Returns (worker_acted, what the close escalated)."""
    from tests.agent_headless.unit.flash.test_a_replaced_errand_starts_the_one_he_named import _close
    worker_acted = {"v": None}
    _settle(text, brief, worker_acted, acted=acted, stop_words=False)
    return worker_acted, _close(text, brief, worker_acted, {"v": None, "more": [], "surface": {}}, monkeypatch)


@pytest.mark.parametrize("text", UNRELATED)
@pytest.mark.parametrize("brief", [_m1(), _m1(target="running_errand"), _m1(confidence=0.95)],
                         ids=["unsure-unaimed", "unsure-aimed", "sure-unaimed"])
def test_an_unrelated_question_never_replaces_the_running_errand(text, brief, errand, monkeypatch):
    worker_acted, escalated = _the_turn(text, brief, monkeypatch)
    assert errand["cancelled"] == [] and worker_acted["v"] is None, "the monitor errand was stopped"
    assert not any("It replaces the errand" in e for e in escalated), "a successor was started in its place"


@pytest.mark.parametrize("text", UNRELATED)
def test_a_sure_aimed_replace_over_a_turn_a_card_served_stops_nothing(text, errand, monkeypatch):
    """The chart answered on screen: the turn's request was served, whatever the stop question read."""
    worker_acted, _esc = _the_turn(text, _m1(0.95, "running_errand"), monkeypatch, acted={"widget": True})
    assert errand["cancelled"] == [] and worker_acted["v"] is None


@pytest.mark.parametrize("text", REAL_REPLACES)
def test_a_real_replace_ends_the_errand_and_starts_the_one_he_named(text, errand, monkeypatch):
    worker_acted, escalated = _the_turn(text, _m1(0.95, "running_errand"), monkeypatch)
    assert errand["cancelled"] == [text] and worker_acted["v"] == "stop"
    assert len(escalated) == 1 and escalated[0].startswith(text) and "Monitor the price" in escalated[0]


# ── disarm: the one rule switched off → both regressions come back ──────────────────────────────────────────
def test_the_disarm_without_the_rule_the_correction_reaches_the_errand_and_the_pause_kills_it(errand, monkeypatch):
    monkeypatch.setattr(sd, "card_owns_the_turn", lambda *a, **k: False)
    assert sd.card_owns_the_turn(None) is False, "the disarm landed"
    _note("musica", "play", {"query": "x"})
    acted = {"v": None}
    assert sd.steer(_brief(stop_errand=("steer", 0.95), corrects_last=("corrects_last", 0.95)),
                    CORRECTIONS[0][0], worker_acted=acted) == "9" and acted["v"] == "inject"
    worker_acted = {"v": None}
    _settle(PAUSES[0][0], _brief(stop_errand=("stop", 0.95), screen_action=("musica:pause", 1.0)), worker_acted)
    assert errand["cancelled"] == [PAUSES[0][0]]


# ── drivers ─────────────────────────────────────────────────────────────────────────────────────────────────
_SPEECH = SimpleNamespace(sanitize=lambda s, drop_metadata=False: s)


def _settle(text, brief, worker_acted, *, acted=None, stop_words=True):
    from nucleo.flash import post_stream_settle
    asyncio.run(post_stream_settle.settle_what_is_pending(
        _ans=None, _ask_waiting=False, _auth_pending=False, _brief=brief,
        _dialog=SimpleNamespace(sanitize_reply=lambda s: s), _filler_audio=SimpleNamespace(played_recently=lambda: False),
        _langs=None, _prev_pending=[], _r=None, _resolve_confirm=lambda yes: None,
        _router=SimpleNamespace(looks_like_stop_work=lambda t: stop_words, operator_words=lambda o, t: o),
        _shown_ids=set(), acted=acted or {"widget": False}, aside={"v": False},
        brain=SimpleNamespace(_window=[], _last_spoken=""), clarify={"msg": ""}, confirm_state={"handled": True},
        data_done={"v": None}, emit=lambda *a, **k: None, escalate_req={"v": None, "more": [], "surface": {}},
        had_pending_confirm=True, llm_metrics={}, music_req={"v": None}, operator_text=text, search_req={"v": None},
        send=lambda s: None, speech=_SPEECH, spoken_text="", style_fired={"v": False}, text=text,
        worker_acted=worker_acted))


def _complete(text, brief, monkeypatch, *, repair=None, say="Switching to Like a Prayer."):
    """Drive `post_stream_acts.complete_the_acts` over a turn whose model promised and called nothing; returns
    (its result dict, worker_acted, card ops run). The promise pass proposes `repair`'s call (nothing by default)."""
    from nucleo.flash import act_repair, post_stream_acts, router as _router

    async def _nothing(*a, **k):
        return None
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", repair or _nothing)
    worker_acted, ops = {"v": None}, []
    out = asyncio.run(post_stream_acts.complete_the_acts(
        _apply_widget_data=lambda w, a, p: ops.append((w, a)), _brief=brief, _data_ops_hechas=[], _has_workers=True,
        _prompt_mod=None, _repeat_repair={"v": None}, _router=_router, _show_guard_target=lambda *a: None,
        _tag_emit=lambda *a, **k: None, _tool_fired=set(), _turn_op_tasks=[], acted={"widget": False},
        brain=SimpleNamespace(_window=[], _last_action=None, _last_spoken="", _turn_calls=[]), canvas_h=None,
        clarify={"msg": ""}, cron_seen=set(), data_done={"v": None}, emit=lambda *a, **k: None,
        escalate_req={"v": None, "more": [], "surface": {}}, images_req={"v": None}, listing_req={"v": None},
        music_req={"v": None}, operator_text=text, read_req={"v": None}, recall_req={"v": None},
        reopen_req={"v": None}, reveal_req={"v": None}, search_req={"v": None}, send=lambda s: None, speak=_nothing,
        spec=None, speech=_SPEECH, spoken=[say], text=text, worker_acted=worker_acted))
    return out or {}, worker_acted, ops


def test_every_route_of_his_words_into_an_errand_crosses_the_one_door():
    """Guard: `inject_soon` is for OUR notes to a worker; his words go through `relay_his_words`. A new caller of
    `inject_soon` must be one of ours, or it reopens the R7 class beside the door."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[4]
    ours = {"nucleo/dispatch/soon.py",            # the door itself
            "nucleo/dispatch/prepare.py",         # the research direction WE composed
            "nucleo/flash/worker_note_relay.py"}  # his op on the errand's OWN sheet: that card is the errand's
    callers = {str(p.relative_to(root)) for d in ("nucleo", "voice", "widgets", "connectors", "server")
               for p in (root / d).rglob("*.py") if re.search(r"\binject_soon\(", p.read_text(encoding="utf-8"))
               and "def inject_soon" not in p.read_text(encoding="utf-8")}
    assert callers <= ours, f"his words reach an errand around the owner door: {sorted(callers - ours)}"
