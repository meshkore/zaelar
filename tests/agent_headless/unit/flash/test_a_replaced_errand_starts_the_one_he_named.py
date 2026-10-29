"""A correction of the running errand is one act (V2-820): «not X, Y» stops X AND starts Y; «look there, not here»
reaches X.

Measured on a live session: he asked for an app that would read his sent messages and distil his writing
style; then «no tiene que ser una aplicación… lee cincuenta mensajes y créame ese documento». The model called
`stop_worker` and said «paro lo del widget y me pongo a leer cincuenta de tus mensajes» — the app build stopped and
nothing started. Three minutes later: «te he pedido una cosa y creo que me estás ignorando». The stop question had
two answers, «stop» and «keep», and a stop door never lets the turn's escalation through.

Later, with the document errand running: «no quiero que mires WhatsApp, quiero que mires el email». The reply
promised «le digo al proceso que se limite a tu correo»; nothing told the process — the promise pass opened his
mail card instead — and the worker kept reading WhatsApp.

The turn's brief now answers four ways while an errand runs: stop · replace · steer · keep. A sure `replace` stops
the errand AND the turn carries its replacement, with the stopped errand's goal beside his words; a sure `steer`
relays his words to the ONE running errand before any repair pass can turn the promise into a card op.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.request import stop as sd

#: «not X, do Y» in several languages — the stopped errand is the app build, the new one the document.
REPLACE_BANK = [
    ("No hay que crear una app, hay que crear un documento con mi estilo",
     "Crear una app que lea mis mensajes enviados de más de 50 caracteres"),
    ("Forget the app — just read fifty of my sent emails and write me a document about how I write",
     "Build an app that reads my sent messages longer than 50 characters"),
    ("Pas d'application : écris-moi un document sur mon style",
     "Créer une application qui lit mes messages envoyés"),
]

#: «look there, not here» — the errand goes on with his correction.
STEER_BANK = [
    "No quiero que mires WhatsApp. Quiero que mires el email.",
    "Don't look at WhatsApp, look at my email instead.",
    "WhatsAppじゃなくてメールを見て",
]


def _brief(choice: str | None, confidence: float = 0.95):
    ev = threading.Event()
    ev.set()
    result = {} if choice is None else {sd.KEY: {"choice": choice, "confidence": confidence}}
    if choice == "replace":   # V2-831 T-19 R15: a replace is a verdict only when it is aimed at the running errand
        result["errand_target"] = {"choice": "running_errand", "confidence": 0.9}
    return {"event": ev, "turn_id": "t-1", "open_ids": [], "result": result}


@pytest.fixture
def one_errand(monkeypatch):
    """One live errand, id «7», goal «the app build»; records what was cancelled and injected."""
    from nucleo import dispatch
    seen = {"cancelled": [], "injected": []}
    rec = SimpleNamespace(goal="Crear una app que lea mis mensajes enviados", waiting_on="")
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: ["7"])
    monkeypatch.setattr(dispatch, "get_record", lambda tid: rec if str(tid) == "7" else None)
    monkeypatch.setattr(dispatch, "has_active", lambda: True)
    monkeypatch.setattr(dispatch, "cancel_soon", lambda w: seen["cancelled"].append(w) or ["7"])
    monkeypatch.setattr(dispatch, "inject_soon", lambda w, m: seen["injected"].append((w, m)))
    seen["rec"] = rec
    return seen


# ── replace: one act ─────────────────────────────────────────────────────────────────────────────────────────
def _stopped(goal):
    return {"v": "stop", "stopped": [goal]}


@pytest.mark.parametrize("text,old_goal", REPLACE_BANK)
def test_a_replace_ends_the_errand_like_a_stop(text, old_goal, one_errand):
    assert sd.model_stop(_brief("replace"), grammar=False) == "run", "the tool gate lets the model's stop run"
    acted: dict = {}
    assert sd.repair(_brief("replace"), text, escalating=True, grammar=lambda: False, acted=acted) == ["7"], \
        "a turn that also escalated still stops the errand it replaces"
    assert acted["stopped"] == ["Crear una app que lea mis mensajes enviados"], "the goal is read before the cancel"


@pytest.mark.parametrize("text,old_goal", REPLACE_BANK)
def test_a_replace_starts_the_errand_he_named_with_the_old_goal_carried(text, old_goal):
    req = {"v": None, "more": []}
    said: list = []
    assert sd.start_beside_the_stop(_brief("replace"), req, text, _stopped(old_goal), emit=lambda *a, **k: said.append(a))
    assert said, "the replacement is said on the timeline"
    assert req["v"].startswith(text), "his words of this turn are the request"
    assert old_goal in req["v"], "what he had asked in the stopped errand is carried, not lost with the cancel"
    assert req["replaces"] == [old_goal]


def test_the_models_own_escalation_keeps_its_words_and_gains_the_carried_goal():
    req = {"v": "Leer 50 correos enviados y redactar un documento con su estilo", "more": []}
    assert sd.start_beside_the_stop(_brief("replace"), req, "no, un documento", _stopped("la app"))
    assert req["v"].startswith("Leer 50 correos enviados") and "la app" in req["v"]


def test_no_stop_this_turn_means_nothing_to_replace():
    req = {"v": None, "more": []}
    assert not sd.start_beside_the_stop(_brief("replace"), req, "un documento", {"v": None})
    assert not sd.start_beside_the_stop(_brief("replace"), req, "un documento", {"v": "inject"})
    assert req["v"] is None


@pytest.mark.parametrize("choice", ["stop", "keep", "steer", None])
def test_only_a_sure_replace_starts_anything(choice):
    req = {"v": None, "more": []}
    assert not sd.start_beside_the_stop(_brief(choice), req, "no, un documento", _stopped("la app"))
    assert req["v"] is None and "replaces" not in req
    assert not sd.start_beside_the_stop(_brief("replace", confidence=0.2), req, "x", _stopped("y")), "unsure → today"


def test_the_goal_is_read_before_the_cancel_purges_it(one_errand):
    assert sd.goals_of("todo") == ["Crear una app que lea mis mensajes enviados"]


_SPEECH = SimpleNamespace(sanitize=lambda s, drop_metadata=False: s)


def test_the_tool_gate_records_what_its_stop_ended(one_errand):
    """The voice tool gate: the model's `stop_worker` over a sure replace runs, and the turn keeps the stopped goal."""
    from nucleo.flash import tool_executor_calls as _calls
    acted = {"v": None}
    _calls._t_stop_worker(args={"which": "la app"}, _norm_nfkd=str.lower, _say=lambda: None,
                          _says_stop=lambda t: False, clarify={}, emit=lambda *a, **k: None,
                          text=REPLACE_BANK[1][0], worker_acted=acted, brief=_brief("replace"), prior="")
    assert one_errand["cancelled"] == ["la app"] and acted["v"] == "stop"
    assert acted["stopped"] == ["Crear una app que lea mis mensajes enviados"]


def _settle(text, brief, worker_acted):
    import asyncio
    from nucleo.flash import post_stream_settle
    asyncio.run(post_stream_settle.settle_what_is_pending(
        _ans=None, _ask_waiting=False, _auth_pending=False, _brief=brief,
        _dialog=SimpleNamespace(sanitize_reply=lambda s: s), _filler_audio=SimpleNamespace(played_recently=lambda: False),
        _langs=None, _prev_pending=[], _r=None, _resolve_confirm=lambda yes: None,
        _router=SimpleNamespace(looks_like_stop_work=lambda t: False, operator_words=lambda o, t: o),
        _shown_ids=set(), acted={"widget": False}, aside={"v": False},
        brain=SimpleNamespace(_window=[], _last_spoken=""), clarify={"msg": ""}, confirm_state={"handled": True},
        data_done={"v": None}, emit=lambda *a, **k: None, escalate_req={"v": None, "more": [], "surface": {}},
        had_pending_confirm=True, llm_metrics={}, music_req={"v": None}, operator_text=text, search_req={"v": None},
        send=lambda s: None, speech=_SPEECH, spoken_text="", style_fired={"v": False}, text=text,
        worker_acted=worker_acted))


def test_the_settle_step_records_what_its_backstop_ended(one_errand):
    """The voice backstop: the model called nothing over a sure replace — the errand stops and its goal is kept."""
    acted = {"v": None}
    _settle(REPLACE_BANK[2][0], _brief("replace"), acted)
    assert one_errand["cancelled"] and acted["v"] == "stop"
    assert acted["stopped"] == ["Crear una app que lea mis mensajes enviados"]


def _close(text, brief, worker_acted, escalate_req, monkeypatch) -> list:
    """Drive the voice turn's close (`turn_after.close_the_turn`) and return what it escalated."""
    import asyncio
    from nucleo.flash import router as _router
    from voice.engine.llm.providers import nucleo as _p, turn_after
    monkeypatch.setattr(_p, "_similar_pending", lambda req, prev: True)   # the request is VERY like the dying one
    escalated: list = []
    asyncio.run(turn_after.close_the_turn(
        send=lambda s: None, _acc_ms=0, _amap_ms=0, _brief=brief, _busy_at_start=None,
        _dialog=SimpleNamespace(push_user=lambda w, t: None, sanitize_reply=lambda s: s, prune_window=lambda w: w,
                                record_silent_action=lambda w, s: None),
        _escalate_mod=SimpleNamespace(escalate_to_slowbrain=lambda req, context=None: escalated.append(req),
                                      done_when_from_brief=lambda b: None, class_verdict=lambda b: None),
        _filler_audio=SimpleNamespace(note_latency=lambda ms: None, played_recently=lambda: False),
        _gate_ms=0, _op_text=text, _prev_pending=[{"request": "la app"}],
        _router=_router, _shown_ids=set(), _start_web_auth=lambda s: False,
        _t_entry=0.0, _t_stream0=0.0, _tool_fired=set(), _turn_tools=[], acted={"widget": False},
        aside={"v": True}, attention=SimpleNamespace(was_typed=lambda: False),
        brain=SimpleNamespace(_window=[], _turn_count=0, _last_spoken="", _turn_calls=[]),
        clarify={"msg": ""}, confirm_state={}, data_done={"v": None}, deduped={"v": False},
        emit=lambda *a, **k: None, escalate_req=escalate_req, first_ms=None, first_turn=True,
        images_req={"v": None}, listing_req={"v": None}, llm_metrics={}, music_req={"v": None}, operator_text=text,
        read_req={"v": None}, recall_req={"v": None}, reopen_req={"v": None}, reveal_req={"v": None},
        search_req={"v": None}, spec=SimpleNamespace(provider="p", model="m"), speech=_SPEECH,
        spoken_text="Vale, paro eso y me pongo con lo nuevo.", style_fired={"v": False}, system="", t0=0.0,
        text=text, timings={}, worker_acted=worker_acted))
    return escalated


@pytest.mark.parametrize("text,old_goal", REPLACE_BANK[:2])
def test_the_turn_close_starts_the_replacement_beside_the_stop(text, old_goal, monkeypatch):
    """The voice turn's close: a turn that stopped an errand over a sure replace still starts the work he named —
    with the stopped goal carried — and never as a refinement injected into the errand it just killed."""
    from nucleo import dispatch
    monkeypatch.setattr(dispatch, "inject_soon", lambda *a: pytest.fail("a replacement was injected into the dying errand"))
    esc = {"v": None, "more": [], "surface": {}}
    escalated = _close(text, _brief("replace"), {"v": "stop", "stopped": [old_goal]}, esc, monkeypatch)
    assert len(escalated) == 1 and escalated[0].startswith(text) and old_goal in escalated[0]


@pytest.mark.parametrize("choice", ["stop", "keep"])
def test_the_turn_close_starts_nothing_after_a_plain_stop(choice, monkeypatch):
    esc = {"v": None, "more": [], "surface": {}}
    assert _close("para eso", _brief(choice), {"v": "stop", "stopped": ["la app"]}, esc, monkeypatch) == []


def test_the_disarm_a_close_that_ignores_the_replace_starts_nothing(monkeypatch):
    """Disarm: the close no longer composes the replacement → the stop stands alone and his new work is lost."""
    monkeypatch.setattr(sd, "start_beside_the_stop", lambda *a, **k: False)
    esc = {"v": None, "more": [], "surface": {}}
    text, old = REPLACE_BANK[0]
    assert _close(text, _brief("replace"), {"v": "stop", "stopped": [old]}, esc, monkeypatch) == []


# ── steer: his correction reaches the errand ────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", STEER_BANK)
def test_a_steer_reaches_the_one_running_errand(text, one_errand):
    acted, esc = {"v": None}, {"v": "leer mis correos", "more": ["x"]}
    assert sd.steer(_brief("steer"), text, worker_acted=acted, escalate_req=esc) == "7"
    assert one_errand["injected"] == [("7", " ".join(text.split()))]
    assert acted["v"] == "inject", "the turn now counts as acted: no repair pass turns the promise into a card op"
    assert esc == {"v": None, "more": []}, "the model's escalation of his correction is the relay's, not a new errand"


@pytest.mark.parametrize("choice", ["keep", "stop", "replace", None])
def test_only_a_sure_steer_relays(choice, one_errand):
    acted = {"v": None}
    assert sd.steer(_brief(choice), STEER_BANK[0], worker_acted=acted) == ""
    assert one_errand["injected"] == [] and acted["v"] is None


def test_a_steer_never_doubles_what_the_model_already_did(one_errand):
    for already in ("inject", "answer", "stop"):
        assert sd.steer(_brief("steer"), STEER_BANK[1], worker_acted={"v": already}) == ""
    assert one_errand["injected"] == []


def test_a_steer_with_several_errands_or_one_waiting_on_him_is_left_to_today(one_errand, monkeypatch):
    from nucleo import dispatch
    one_errand["rec"].waiting_on = "¿Cuántos mensajes?"
    assert sd.steer(_brief("steer"), STEER_BANK[0], worker_acted={"v": None}) == "", "its answer is another door"
    one_errand["rec"].waiting_on = ""
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda q: ["7", "8"])
    assert sd.steer(_brief("steer"), STEER_BANK[0], worker_acted={"v": None}) == "", "never a guess between two"
    assert one_errand["injected"] == []


def _complete(text, brief, monkeypatch, *, promise="Vale, le digo al proceso que mire solo tu correo."):
    """Drive the voice turn's act completion (`post_stream_acts.complete_the_acts`) over a turn whose model PROMISED
    and called nothing, with his mail card named by the catalogue. Returns (card ops run, promise passes asked)."""
    import asyncio
    from nucleo.flash import act_repair, card_commission, post_stream_acts, router as _router
    passes: list = []

    async def _pass(*a, **k):
        passes.append(a)
        return {"widget_id": "mensajes", "action": "open_thread", "payload": {"q": "email"}}
    monkeypatch.setattr(act_repair, "call_for_promise_or_order", _pass)
    monkeypatch.setattr(card_commission, "named_or_catalogue", lambda brief, text: "mensajes")
    ops: list = []

    async def _speak(*a, **k):
        return None
    worker_acted = {"v": None}
    asyncio.run(post_stream_acts.complete_the_acts(
        _apply_widget_data=lambda w, a, p: ops.append((w, a)), _brief=brief, _data_ops_hechas=[], _has_workers=True,
        _prompt_mod=None, _repeat_repair={"v": None}, _router=_router, _show_guard_target=lambda *a: None,
        _tag_emit=lambda *a, **k: None, _tool_fired=set(), _turn_op_tasks=[], acted={"widget": False},
        brain=SimpleNamespace(_window=[], _last_action=None, _last_spoken="", _turn_calls=[]), canvas_h=None,
        clarify={"msg": ""}, cron_seen=set(), data_done={"v": None}, emit=lambda *a, **k: None,
        escalate_req={"v": None, "more": [], "surface": {}}, images_req={"v": None}, listing_req={"v": None},
        music_req={"v": None}, operator_text=text, read_req={"v": None}, recall_req={"v": None},
        reopen_req={"v": None}, reveal_req={"v": None}, search_req={"v": None}, send=lambda s: None, speak=_speak,
        spec=None, speech=SimpleNamespace(sanitize=lambda s, drop_metadata=False: s), spoken=[promise], text=text,
        worker_acted=worker_acted))
    return ops, passes, worker_acted


@pytest.mark.parametrize("text", STEER_BANK[:2])
def test_a_steer_reaches_the_errand_and_no_promise_pass_turns_it_into_a_card_op(text, one_errand, monkeypatch):
    """The voice act completion: the promise «le digo al proceso…» is KEPT by the relay — his mail card is not
    opened in its place (the live bug), and no second pass is even asked."""
    ops, passes, acted = _complete(text, _brief("steer"), monkeypatch)
    assert one_errand["injected"] == [("7", " ".join(text.split()))]
    assert acted["v"] == "inject" and ops == [] and passes == []


def test_the_disarm_a_steer_that_does_not_relay_lets_the_promise_pass_open_the_card(one_errand, monkeypatch):
    """Disarm: the relay is switched off → the same turn reaches the promise pass, and the card op runs instead."""
    monkeypatch.setattr(sd, "steer", lambda *a, **k: "")
    ops, passes, acted = _complete(STEER_BANK[0], _brief("steer"), monkeypatch)
    assert one_errand["injected"] == [] and passes and ops == [("mensajes", "open_thread")]


def test_the_question_offers_its_answers():
    assert set(sd.question("")["criteria"]) == {"stop", "stop_all", "replace", "steer", "settled", "keep"}   # T-29: settled
    assert [c for c in sd.CHOICES if sd.ends(c)] == ["stop", "stop_all", "replace", "settled"]


# ── steer: words a card already carried out are not a correction of the errand (demo sandbox 2026-10-28) ──────
@pytest.mark.parametrize("text", ["set the first one as my background", "actually move it half an hour later",
                                  "pon la primera de fondo", "muévela media hora más tarde"])
@pytest.mark.parametrize("consumed", [{"acted": {"widget": True}}, {"data_done": {"v": True}}])
def test_an_order_a_card_carried_out_is_never_relayed_to_the_errand(text, consumed, one_errand):
    """B2 and C4: the wallpaper was set, the meeting moved — and the same words went to the monitor errand as a
    «steer»; the worker stopped to ask which image, which meeting, and his next order answered THAT. One sentence,
    one order: the act on the card consumed it."""
    acted = {"v": None}
    assert sd.steer(_brief("steer"), text, worker_acted=acted, **consumed) == ""
    assert one_errand["injected"] == [] and acted["v"] is None


def test_a_lane_that_carried_the_words_out_consumes_them_too(one_errand):
    """U2 «no, put like a prayer» played the track (the music lane) AND was relayed to the monitor errand."""
    acted = {"v": None}
    assert sd.steer(_brief("steer"), "no, put like a prayer", worker_acted=acted, lanes=({"v": {"query": "Like a Prayer"}}, {"v": None})) == ""
    assert one_errand["injected"] == []


@pytest.mark.parametrize("sure, relayed", [(True, ""), (False, "7")])
def test_a_verdict_that_surely_names_a_cards_act_keeps_the_words_on_the_card(one_errand, monkeypatch, sure, relayed):
    """S2 «compare them side by side»: `results:layout` at 1.00 — the sheet's own act, not a correction of the errand."""
    from nucleo.flash import direct_action as DA
    monkeypatch.setattr(DA, "from_brief", lambda b: ("results::723152-ls1", "layout"))
    monkeypatch.setattr(DA, "_action_sure", lambda b, floor=0.8: sure)
    acted = {"v": None}
    assert sd.steer(_brief("steer"), "compare them side by side", worker_acted=acted) == relayed


def test_a_steer_nothing_carried_out_still_reaches_the_errand(one_errand):
    acted = {"v": None}
    assert sd.steer(_brief("steer"), STEER_BANK[1], worker_acted=acted, acted={"widget": False},
                    data_done={"v": False}) == "7"
    assert one_errand["injected"]
