"""A card action the turn runs comes on screen only when the turn asked to SEE it (V2-815).

Measured on a phone, 2026-10-26: «busca el programa que está en tu web», «retoma la búsqueda de Draper», «check
hacker news, locate my post» — the brief said `canvas = neither` every time and the browser card took the whole
screen three times anyway: the catalogue rung (`card_commission.before_worker`) and the promise repair presented
every call as a `turn-order`. A search is work done behind the screen; its findings go to the errand's sheet.

`canvas_visibility.present_for_call` is the one rule: the card comes up for a `present.mount` action, for a lens
(`data.read`) over a closed card, or when the verdict says `canvas = show` — never on habit. Each case below varies
the widget and the action, so a fix that names the browser would not pass.
"""
from __future__ import annotations

import pytest

from nucleo.flash import canvas_visibility as cv
from nucleo.turn import brief as tb


@pytest.fixture()
def shows(monkeypatch):
    out: list = []
    monkeypatch.setattr(cv, "is_open", lambda wid, known=None: False)
    monkeypatch.setattr(cv, "is_minimized", lambda wid: False)
    return out


def _emit(out):
    return lambda kind, label, extra=None, **k: out.append((label, dict(extra or {})))


def _verdict(monkeypatch, canvas):
    monkeypatch.setattr(tb, "read", lambda b, key, d="", min_confidence=None:
                        ((canvas, {"used": True}) if key == tb.CANVAS_KEY and canvas else (d, None)))


@pytest.mark.parametrize("wid,action", [("navegador", "automate"), ("navegador", "open"), ("mensajeria", "send")])
def test_a_write_with_no_show_in_the_turn_runs_behind_the_screen(monkeypatch, shows, wid, action):
    _verdict(monkeypatch, "neither")
    assert cv.present_for_call(wid, action, brief={"x": 1}, emit=_emit(shows)) is False
    assert [l for l, _ in shows] == ["🚫 presentación suprimida"], shows
    assert "detrás de la pantalla" in shows[0][1]["detail"]


def test_no_verdict_is_no_show(monkeypatch, shows):
    _verdict(monkeypatch, "")
    assert cv.present_for_call("navegador", "automate", brief=None, emit=_emit(shows)) is False
    assert not [l for l, _ in shows if l == "show"]


@pytest.mark.parametrize("wid,action", [("navegador", "open"), ("agenda", "add_event")])
def test_a_turn_that_asks_to_see_it_brings_the_card(monkeypatch, shows, wid, action):
    _verdict(monkeypatch, "show")
    assert cv.present_for_call(wid, action, brief={"x": 1}, emit=_emit(shows)) is True
    assert shows[-1][0] == "show" and shows[-1][1]["id"] == wid and shows[-1][1]["reason"] == "turn-order"


def test_an_output_that_only_exists_on_screen_brings_its_card_whatever_the_verdict(monkeypatch, shows):
    _verdict(monkeypatch, "neither")
    assert cv.present_for_call("musica", "play", brief={"x": 1}, emit=_emit(shows)) is True
    assert shows[-1][1]["reason"] == "producer-mount"


def test_a_lens_over_a_closed_card_brings_it(monkeypatch, shows):
    _verdict(monkeypatch, "neither")
    assert cv.present_for_call("agenda", "show_day", brief={"x": 1}, emit=_emit(shows)) is True
    assert shows[-1][1]["reason"] == "turn-order"


def test_the_card_presented_is_the_one_the_caller_narrowed_to(monkeypatch, shows):
    _verdict(monkeypatch, "show")
    cv.present_for_call("results", "present", brief={"x": 1}, card="results::abc-1", emit=_emit(shows))
    assert shows[-1][1]["id"] == "results::abc-1"


# ── the rungs that run a card action ahead of a worker: each one, driven, under `canvas = neither` ──────────────
def _rung_catalogue(monkeypatch, out, wid, action) -> list:
    """The catalogue rung (`card_commission.before_worker`) took the errand. Returns the card ops it ran."""
    import asyncio
    from nucleo.flash import card_commission as cc

    async def _got(*a, **k):
        return {"kind": "call", "widget_id": wid, "action": action, "payload": {}}
    monkeypatch.setattr(cc, "commission_call", _got)
    ops: list = []
    esc = {"v": "busca el programa que está en mi web", "more": [], "surface": {}}
    assert asyncio.run(cc.before_worker(esc, {"v": None}, brief={"x": 1}, operator_text=esc["v"], spec=None,
                                        emit=_emit(out), present=lambda *a, **k: pytest.fail("presented on habit"),
                                        apply_widget_data=lambda w, a, p: ops.append((w, a)))) == "call"
    return ops


def _rung_instead_of_a_search(monkeypatch, out, wid, action) -> list:
    """The card that answers a search the model sent to the web (`card_commission.voice_instead_of_a_search`)."""
    import asyncio
    from nucleo.flash import card_commission as cc

    async def _got(*a, **k):
        return {"kind": "call", "widget_id": wid, "action": action, "payload": {}}
    monkeypatch.setattr(cc, "instead_of_a_search", _got)
    ops: list = []
    asyncio.run(cc.voice_instead_of_a_search({"v": "hacker news my post"}, {"v": None}, brief={"x": 1},
                                             operator_text="check hacker news, locate my post", spec=None, window=[],
                                             emit=_emit(out), present=lambda *a, **k: pytest.fail("presented on habit"),
                                             apply_widget_data=lambda w, a, p: ops.append((w, a)),
                                             acted={"widget": False}, done={"v": None}))
    return ops


def _complete_the_acts(monkeypatch, out, *, data_done, spoken):
    import asyncio
    from types import SimpleNamespace
    from nucleo.flash import post_stream_acts, router as _router
    ops: list = []

    async def _speak(*a, **k):
        return None
    asyncio.run(post_stream_acts.complete_the_acts(
        _apply_widget_data=lambda w, a, p: ops.append((w, a)), _brief={"x": 1}, _data_ops_hechas=[], _has_workers=False,
        _prompt_mod=None, _repeat_repair={"v": None}, _router=_router, _show_guard_target=lambda *a: None,
        _tag_emit=lambda *a, **k: None, _tool_fired=set(), _turn_op_tasks=[], acted={"widget": False},
        brain=SimpleNamespace(_window=[], _last_action=None, _last_spoken="", _turn_calls=[]), canvas_h=None,
        clarify={"msg": ""}, cron_seen=set(), data_done=data_done, emit=_emit(out),
        escalate_req={"v": None, "more": [], "surface": {}}, images_req={"v": None}, listing_req={"v": None},
        music_req={"v": None}, operator_text="retoma la búsqueda de Draper", read_req={"v": None},
        recall_req={"v": None}, reopen_req={"v": None}, reveal_req={"v": None}, search_req={"v": None},
        send=lambda s: None, speak=_speak, spec=None, speech=SimpleNamespace(sanitize=lambda s, drop_metadata=False: s),
        spoken=spoken, text="retoma la búsqueda de Draper", worker_acted={"v": None}))
    return ops


def _rung_promise(monkeypatch, out, wid, action) -> list:
    """The promise repair: the reply promised an act on a card the catalogue names, and called nothing."""
    from nucleo.flash import act_repair, card_commission as cc

    async def _got(*a, **k):
        return {"widget_id": wid, "action": action, "payload": {}}
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", _got)
    monkeypatch.setattr(cc, "named_or_catalogue", lambda brief, text: wid)
    return _complete_the_acts(monkeypatch, out, data_done={"v": None}, spoken=["Me pongo con la búsqueda ahora."])


def _rung_order_after_read(monkeypatch, out, wid, action) -> list:
    """The order on ANOTHER card than the one the turn touched (`order_card_after_read` + `call_after_read`)."""
    from nucleo.flash import act_repair, post_stream as _pst

    async def _got(*a, **k):
        return {"widget_id": wid, "action": action, "payload": {}}
    monkeypatch.setattr(act_repair, "call_after_read", _got)
    monkeypatch.setattr(_pst._direct_action, "order_card_after_read", lambda brief, text, card: wid)
    return _complete_the_acts(monkeypatch, out, data_done={"v": True, "ops": [("agenda", "add_event")]},
                              spoken=["Hecho."])


RUNGS = [_rung_catalogue, _rung_instead_of_a_search, _rung_promise, _rung_order_after_read]


@pytest.fixture()
def arbiter_allows(monkeypatch):
    """The canvas arbiter downstream lets every show through, so what is measured is the rung's OWN rule — a rung
    may not lean on a later veto (an arbiter that breaks fails open)."""
    from nucleo.acts import canvas_arbiter as arb
    monkeypatch.setattr(arb, "decide", lambda *a, **k: arb.Verdict(allow=True, rule="test-allows", evidence={}))


@pytest.mark.parametrize("rung", RUNGS, ids=lambda r: r.__name__)
@pytest.mark.parametrize("wid,action,canvas", [("navegador", "automate", "neither"), ("mensajeria", "send", "")])
def test_every_repair_rung_runs_its_action_behind_the_screen(monkeypatch, shows, arbiter_allows, rung, wid, action,
                                                             canvas):
    """Each rung that runs a card action ahead of a worker RUNS it and does not bring the card up when the turn did
    not ask to see it (`neither`, or no canvas verdict at all) — whichever card and action, so a fix that names the
    browser would not pass."""
    _verdict(monkeypatch, canvas)
    assert (wid, action) in rung(monkeypatch, shows, wid, action), "the action itself runs"
    assert not [x for lbl, x in shows if lbl == "show"], shows
    assert any(lbl == "🚫 presentación suprimida" and x.get("id") == wid for lbl, x in shows), "the refusal is said"


@pytest.mark.parametrize("rung", RUNGS, ids=lambda r: r.__name__)
def test_every_repair_rung_brings_the_card_when_the_turn_asked_to_see_it(monkeypatch, shows, arbiter_allows, rung):
    _verdict(monkeypatch, "show")
    rung(monkeypatch, shows, "navegador", "automate")
    assert [x["id"] for lbl, x in shows if lbl == "show"] == ["navegador"], shows


@pytest.mark.parametrize("rung", RUNGS, ids=lambda r: r.__name__)
def test_the_disarm_a_rung_that_presents_on_habit_covers_the_screen(monkeypatch, shows, arbiter_allows, rung):
    """Disarm: the rule is replaced by the old habit (every call presented as a `turn-order`) → the card comes up
    under `canvas = neither`, which the behaviour test above refuses."""
    real = cv.present_for_call
    monkeypatch.setattr(cv, "present_for_call", lambda wid, action, *, brief=None, card="", src="flash", emit=None,
                        known=None: cv.present(card or wid, reason="turn-order", action=action, src=src, emit=emit,
                                               brief=brief))
    assert cv.present_for_call is not real
    _verdict(monkeypatch, "neither")
    rung(monkeypatch, shows, "navegador", "automate")
    assert [x["id"] for lbl, x in shows if lbl == "show"] == ["navegador"], shows
