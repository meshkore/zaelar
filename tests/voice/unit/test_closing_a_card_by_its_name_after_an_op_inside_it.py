"""«Stop the video and close youtube»: the op inside the card runs, and the card he NAMED closes after it.

Demo pass 2026-09-28 (V7, two passes running): the model called `youtube:close` — which empties the player, as
its manifest says — and the card stayed open, hiding every card after it. The canvas verdict cannot tell the two
orders apart (measured: Jev reads «close the video» 0.99 and «close youtube» 0.99 both as canvas=close), and
«close the video» must keep the card (V2-753). What separates them is whether his words call the card by what it
is CALLED — its catalogue name in any bundle — or only by what it holds."""
import pytest

from nucleo.flash import direct_action as da

@pytest.fixture
def close_verdict(monkeypatch):
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", lambda brief, key, default="", min_confidence=0.0:
                        ("close", {}) if key == tb.CANVAS_KEY else (default, {}))
    monkeypatch.setattr(da, "_open_now", lambda: ["youtube", "agenda"])


@pytest.mark.parametrize("said", ["ok stop the video and close youtube", "para el vídeo y cierra YouTube"])
def test_the_card_called_by_its_name_closes_after_the_op(close_verdict, said):
    assert da.closes_the_named_card({}, said, [("youtube", "close")]) == "youtube"


@pytest.mark.parametrize("said", ["close the video", "quita el vídeo"])
def test_the_video_named_by_what_the_card_holds_keeps_the_card(close_verdict, said):
    assert da.closes_the_named_card({}, said, [("youtube", "close")]) == ""


def test_the_name_is_read_in_every_catalogue_language():
    names = {n.casefold() for n in da.catalogue_names("agenda")}
    assert {"agenda", "calendar"} <= names
    assert "video" not in {n.casefold() for n in da.catalogue_names("youtube")}, "an alias is not the card's name"


def test_a_card_that_is_not_open_is_not_closed(close_verdict):
    assert da.closes_the_named_card({}, "stop the map and close the map", [("map", "clear")]) == ""


def _forget_the_turn():
    """What a turn leaves behind in process state (the card in focus, the closes it made), given back."""
    from nucleo import canvas_closes, canvas_focus, done_ops
    from nucleo.flash import bulk_close, canvas_license
    canvas_focus._reset()
    done_ops.reset()
    bulk_close.reset()
    canvas_closes._reset_for_tests()
    canvas_license._RECENT_CLOSES.clear()


def _voice_turn(phrase: str, lang: str = "en"):
    """The model runs an op INSIDE the calendar (`show_day`) and calls nothing else; the canvas verdict reads close.
    Through the voice turn itself (the bank harness: the real `run_turn`, every consequence door dry)."""
    from tests.brain import harness as H
    case = {"id": "named-close-after-op", "lang": lang, "phrase": phrase, "source": "node 2.126",
            "screen": {"open": ["agenda", "youtube"]}, "expect": "talk",
            "model": {"say": "", "tools": [{"name": "widget_data", "args": {
                "widget_id": "agenda", "action": "show_day", "payload": {"date": "tomorrow"}}}]},
            "brief": {"canvas": ["close", 0.99], "screen_action": ["agenda:show_day", 0.9], "request_type": ["order", 1.0]}}
    try:
        out = H.run_case(case)
    finally:
        _forget_the_turn()
    assert not out.error, out.error
    return out


@pytest.mark.parametrize("said,lang", [("show me tomorrow and then close the calendar", "en"),
                                       ("enséñame mañana y luego cierra la agenda", "es")])
def test_the_turn_wires_it(said, lang):
    """Another card than the incident's (the calendar, not the player — a player's stop under a close verb has its
    own door, `card_close.data_close`): the op runs, then the card he called by its name closes."""
    out = _voice_turn(said, lang)
    assert out.decision == "data-op agenda:show_day" and "close agenda" in out.also, out.all_decisions


def test_the_disarm_no_named_close_leaves_the_card_after_the_op(monkeypatch):
    monkeypatch.setattr(da, "closes_the_named_card", lambda *a, **k: "")
    assert da.closes_the_named_card({}, "close the calendar", [("agenda", "show_day")]) == "", "the mutation landed"
    out = _voice_turn("show me tomorrow and then close the calendar")
    assert out.all_decisions == ["data-op agenda:show_day"], out.all_decisions


def _tag_close(extra: dict, said: str, monkeypatch):
    """One close tag through the tag door (`tool_executor_widget_calls._tag_emit`), over a turn whose sure verdict is
    an action INSIDE the video card. Returns (crossed, events): False is the door's own refusal."""
    import threading
    from types import SimpleNamespace
    from nucleo.flash import tool_executor_widget_calls as calls
    ev = threading.Event()
    ev.set()
    brief = {"event": ev, "turn_id": "t-tag", "open_ids": ["youtube", "agenda"], "result": {
        "screen_action": {"choice": "youtube:close", "confidence": 0.99},
        "canvas": {"choice": "close", "confidence": 0.99}, "request_type": {"choice": "order", "confidence": 1.0}}}
    import server.voice_api as va
    monkeypatch.setattr(va, "open_instances", lambda: ["youtube", "agenda"])
    events = []
    kw = {n: (lambda *a, **k: None) for n in ("_apply_widget_data", "_is_meta_widget_question", "_norm_nfkd",
                                              "_on_tool_call", "_request_delete_confirm", "_show_guard_target",
                                              "_show_target_instance", "_spawn")}
    try:
        got = calls._tag_emit("close", dict(extra), _brief=brief, _shown_ids=set(), acted={"widget": False}, aside={},
                              brain=SimpleNamespace(_window=[], _last_action="", _last_spoken=""), canvas_h=brief,
                              cron_seen=set(), deduped={"v": False}, escalate_req={"v": None}, text=said,
                              emit=lambda kind, label, **k: events.append((kind, label)), **kw)
    finally:
        _forget_the_turn()
    return got is not False, events


def test_the_in_card_guard_lets_the_named_close_through(monkeypatch):
    """full18 V7: the close was emitted and the «order is an action INSIDE the card» guard dropped it. The close the
    turn makes after the op carries `named`, and the guard lets it through over a sure verdict inside the card."""
    monkeypatch.setattr(da, "_says_the_name", lambda *a, **k: False)   # the flag alone, not the other exemption
    crossed, events = _tag_close({"id": "youtube", "named": True}, "ok stop the video and close youtube", monkeypatch)
    assert crossed and ("widget", "close") in events, events


def test_the_disarm_the_same_close_without_the_flag_is_dropped_as_an_inside_order(monkeypatch):
    from nucleo.acts import card_verdict as cv
    monkeypatch.setattr(da, "_says_the_name", lambda *a, **k: False)
    monkeypatch.setattr(cv, "_canvas_leans_close", lambda _b: False)   # node 2.911 licenses it too; this proves the flag
    crossed, events = _tag_close({"id": "youtube"}, "ok stop the video and close youtube", monkeypatch)
    assert not crossed and ("brain", "🛡️ close ignorado — la orden es una acción DENTRO de la tarjeta") in events, events


def test_tidying_the_screen_is_a_canvas_gesture_the_verdict_can_complete(monkeypatch):
    """full21 C5b: «tidy up the screen a bit» → «screen's sorted» with no call; the canvas verdict could only say
    `neither`, because laying the cards out was not one of its gestures."""
    from nucleo.flash import show_target as st
    from nucleo.turn import brief as tb
    assert "arrange" in st.CANVAS_VERBS
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=0.0:
                        ("arrange", {"used": True}) if k == tb.CANVAS_KEY else (d, None))
    ev = []
    assert da.complete_canvas({"x": 1}, tag_emit=lambda a, x: ev.append(("tag", a)),
                              emit=lambda *a, **k: ev.append(a[:2]), operator_text="tidy up the screen") == "arrange"
    assert ("widget", "arrange") in ev and not any(e[0] == "tag" for e in ev)
