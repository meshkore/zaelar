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
import threading
from types import SimpleNamespace

import pytest

from nucleo import done_ops
from nucleo.request import stop as sd

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
    rec = SimpleNamespace(goal="Monitor the price of the Sony headphones", waiting_on="")
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: ["9"])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec if str(tid) == "9" else None)
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: seen["cancelled"].append(w) or ["9"])
    monkeypatch.setattr(dispatch, "inject_soon", lambda w, m: seen["injected"].append((w, m)))
    done_ops.reset()
    yield seen
    done_ops.reset()


# ── R7 · a correction of the last card act stays the card's ─────────────────────────────────────────────────
@pytest.mark.parametrize("text,last", CORRECTIONS)
def test_a_correction_of_the_last_card_act_is_never_steered_to_the_errand(text, last, errand):
    done_ops.note(*last)
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
    done_ops.note(*last)
    out, worker_acted = _complete(text, _brief(stop_errand=("steer", 0.95), corrects_last=("corrects_last", 0.95)),
                                  monkeypatch)
    assert errand["injected"] == []
    assert worker_acted["v"] is None and out.get("_no_tool") is True


def test_an_unsure_correction_does_not_veto_the_steer(errand):
    done_ops.note("musica", "play", {"query": "x"})
    brief = _brief(stop_errand=("steer", 0.95), corrects_last=("corrects_last", 0.6))
    assert sd.steer(brief, REAL_STEERS[0], worker_acted={"v": None}) == "9"


def test_a_correction_with_no_card_act_behind_it_steers(errand):
    """Nothing in the funnel's ledger: the correction cannot be about a card's act — the errand's reading stands."""
    brief = _brief(stop_errand=("steer", 0.95), corrects_last=("corrects_last", 0.95))
    assert sd.steer(brief, REAL_STEERS[1], worker_acted={"v": None}) == "9"


@pytest.mark.parametrize("text", REAL_STEERS)
@pytest.mark.parametrize("redo", [None, ("new_request", 0.95), ("unrelated", 0.99)])
def test_a_real_correction_of_the_errand_still_steers_it(text, redo, errand):
    done_ops.note("musica", "play", {"query": "x"})        # music played earlier: not what he is correcting
    kw = {"corrects_last": redo} if redo else {}
    acted = {"v": None}
    assert sd.steer(_brief(stop_errand=("steer", 0.95), **kw), text, worker_acted=acted) == "9"
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


def test_a_replace_still_ends_the_errand_even_when_its_new_work_is_a_card_act(errand):
    """«Forget the price check, put some music on»: a replace is coherent with a card act — the errand ends."""
    brief = _brief(stop_errand=("replace", 0.95), screen_action=("musica:play", 1.0))
    assert sd.repair(brief, "forget the price check, put some music on", escalating=False, grammar=lambda: False,
                     card_acts={"acted": {"widget": True}}) == ["9"]


# ── disarm: the one rule switched off → both regressions come back ──────────────────────────────────────────
def test_the_disarm_without_the_rule_the_correction_reaches_the_errand_and_the_pause_kills_it(errand, monkeypatch):
    monkeypatch.setattr(sd, "card_owns_the_turn", lambda *a, **k: False)
    assert sd.card_owns_the_turn(None) is False, "the disarm landed"
    done_ops.note("musica", "play", {"query": "x"})
    acted = {"v": None}
    assert sd.steer(_brief(stop_errand=("steer", 0.95), corrects_last=("corrects_last", 0.95)),
                    CORRECTIONS[0][0], worker_acted=acted) == "9" and acted["v"] == "inject"
    worker_acted = {"v": None}
    _settle(PAUSES[0][0], _brief(stop_errand=("stop", 0.95), screen_action=("musica:pause", 1.0)), worker_acted)
    assert errand["cancelled"] == [PAUSES[0][0]]


# ── drivers ─────────────────────────────────────────────────────────────────────────────────────────────────
_SPEECH = SimpleNamespace(sanitize=lambda s, drop_metadata=False: s)


def _settle(text, brief, worker_acted, *, acted=None):
    from nucleo.flash import post_stream_settle
    asyncio.run(post_stream_settle.settle_what_is_pending(
        _ans=None, _ask_waiting=False, _auth_pending=False, _brief=brief,
        _dialog=SimpleNamespace(sanitize_reply=lambda s: s), _filler_audio=SimpleNamespace(played_recently=lambda: False),
        _langs=None, _prev_pending=[], _r=None, _resolve_confirm=lambda yes: None,
        _router=SimpleNamespace(looks_like_stop_work=lambda t: True, operator_words=lambda o, t: o),
        _shown_ids=set(), acted=acted or {"widget": False}, aside={"v": False},
        brain=SimpleNamespace(_window=[], _last_spoken=""), clarify={"msg": ""}, confirm_state={"handled": True},
        data_done={"v": None}, emit=lambda *a, **k: None, escalate_req={"v": None, "more": [], "surface": {}},
        had_pending_confirm=True, llm_metrics={}, music_req={"v": None}, operator_text=text, search_req={"v": None},
        send=lambda s: None, speech=_SPEECH, spoken_text="", style_fired={"v": False}, text=text,
        worker_acted=worker_acted))


def _complete(text, brief, monkeypatch):
    """Drive `post_stream_acts.complete_the_acts` over a turn whose model promised and called nothing; returns
    (its result dict, worker_acted). The promise passes are stubbed to propose nothing."""
    from nucleo.flash import act_repair, post_stream_acts, router as _router

    async def _nothing(*a, **k):
        return None
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", _nothing)
    worker_acted = {"v": None}
    out = asyncio.run(post_stream_acts.complete_the_acts(
        _apply_widget_data=lambda w, a, p: None, _brief=brief, _data_ops_hechas=[], _has_workers=True,
        _prompt_mod=None, _repeat_repair={"v": None}, _router=_router, _show_guard_target=lambda *a: None,
        _tag_emit=lambda *a, **k: None, _tool_fired=set(), _turn_op_tasks=[], acted={"widget": False},
        brain=SimpleNamespace(_window=[], _last_action=None, _last_spoken="", _turn_calls=[]), canvas_h=None,
        clarify={"msg": ""}, cron_seen=set(), data_done={"v": None}, emit=lambda *a, **k: None,
        escalate_req={"v": None, "more": [], "surface": {}}, images_req={"v": None}, listing_req={"v": None},
        music_req={"v": None}, operator_text=text, read_req={"v": None}, recall_req={"v": None},
        reopen_req={"v": None}, reveal_req={"v": None}, search_req={"v": None}, send=lambda s: None, speak=_nothing,
        spec=None, speech=_SPEECH, spoken=["Switching to Like a Prayer."], text=text, worker_acted=worker_acted))
    return out or {}, worker_acted
