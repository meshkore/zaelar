"""«Close the calendar and the messages» closes both (demo pass 2026-09-28, C6: only the calendar closed).

Two faults stacked. The sibling-card reader matched the manifest's name, which is ONE language («Mensajería»),
so the English «messages» named nothing; and `close_widget` ran once per TURN, so a second call for the second
card was dropped. Now the catalogue name in every bundle counts, and each card closes once."""
import pytest

from nucleo.flash import show_target as st
from widgets import instances


def test_a_card_is_named_by_its_translated_catalogue_name():
    assert instances.also_named("close the calendar and the messages", ["agenda", "mensajeria"],
                                exclude=["agenda"]) == ["mensajeria"]
    assert instances.also_named("cierra la agenda y la mensajería", ["agenda", "mensajeria"],
                                exclude=["agenda"]) == ["mensajeria"]
    assert instances.also_named("close the calendar", ["agenda", "mensajeria"], exclude=["agenda"]) == []


@pytest.fixture
def canvas(monkeypatch):
    monkeypatch.setattr(st, "close_target", lambda wid: wid or "")
    import server.voice_api as va
    monkeypatch.setattr(va, "open_instances", lambda: ["agenda", "mensajeria", "youtube"])


def test_one_call_closes_every_card_his_sentence_names(canvas):
    closed, done = [], set()
    st.close_dispatch({"widget_id": "agenda"}, lambda a, x: closed.append((a, x["id"])), lambda *a, **k: None,
                      text="close the calendar and the messages", done=done)
    assert closed == [("close", "agenda"), ("close", "mensajeria")]


def test_a_second_call_for_the_second_card_is_not_dropped_nor_doubled(canvas):
    closed, done = [], set()
    tag = lambda a, x: closed.append(x["id"])  # noqa: E731
    for wid in ("agenda", "mensajeria"):
        st.close_dispatch({"widget_id": wid}, tag, lambda *a, **k: None, text="close the calendar and the messages",
                          done=done)
    assert closed == ["agenda", "mensajeria"], "each card once"


def test_minimize_takes_only_the_card_it_names(canvas):
    closed = []
    st.close_dispatch({"widget_id": "agenda", "mode": "minimize"}, lambda a, x: closed.append((a, x["id"])),
                      lambda *a, **k: None, text="minimize the calendar and the messages", done=set())
    assert closed == [("minimize", "agenda")]


def test_the_in_card_guard_spares_a_card_called_by_its_name():
    """full18 C6: the verdict read `mensajeria:close` (the chat inside) and the guard for «an order INSIDE the card»
    dropped the close of the Messages card he had named. «close the chat» still reaches the chat."""
    from nucleo.flash import direct_action as da
    assert da._says_the_name("close the calendar and the messages", "mensajeria")
    assert not da._says_the_name("close the chat", "mensajeria")
    out = _voice_turn("close the calendar and the messages")
    assert out.all_decisions == ["close agenda", "close mensajeria"], out.all_decisions


def test_the_same_guard_spares_it_in_spanish():
    out = _voice_turn("cierra la agenda y la mensajería", lang="es")
    assert out.all_decisions == ["close agenda", "close mensajeria"], out.all_decisions


def test_the_disarm_a_guard_deaf_to_the_name_drops_the_second_close(monkeypatch):
    """`_says_the_name` off: the verdict's `mensajeria:close` reads as an order INSIDE the card, and the close of the
    Messages card he named is dropped — only the calendar closes, as in full18 C6."""
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "_says_the_name", lambda *a, **k: False)
    assert not da._says_the_name("close the calendar and the messages", "mensajeria"), "the mutation landed"
    out = _voice_turn("close the calendar and the messages")
    assert out.all_decisions == ["close agenda"], out.all_decisions


def _voice_turn(phrase: str, lang: str = "en"):
    """The model calls `close_widget` once per card; the verdict reads the chat INSIDE the messages (full18 C6). Through
    the voice turn itself (the bank harness: the real `run_turn`, every consequence door dry)."""
    from tests.brain import harness as H
    case = {"id": "two-named-cards", "lang": lang, "phrase": phrase, "source": "node 2.127",
            "screen": {"open": ["agenda", "mensajeria", "youtube"]}, "expect": "talk",
            "model": {"say": "", "tools": [{"name": "close_widget", "args": {"widget_id": "agenda"}},
                                           {"name": "close_widget", "args": {"widget_id": "mensajeria"}}]},
            "brief": {"canvas": ["close", 1.0], "screen_action": ["mensajeria:close", 0.95],
                      "request_type": ["order", 1.0]}}
    try:
        out = H.run_case(case)
    finally:
        from nucleo import canvas_closes, canvas_focus, done_ops
        from nucleo.flash import bulk_close, canvas_license
        canvas_focus._reset()
        done_ops.reset()
        bulk_close.reset()
        canvas_closes._reset_for_tests()
        canvas_license._RECENT_CLOSES.clear()
    assert not out.error, out.error
    return out


def test_the_verdicts_own_close_also_takes_the_other_named_card(monkeypatch):
    """full21 C6: the model called nothing, the verdict closed its own card (the messages) and the calendar stayed,
    while the reply said both were off the screen."""
    from nucleo.flash import direct_action as da
    from nucleo.turn import brief as tb
    monkeypatch.setattr(tb, "read", lambda b, k, d="", min_confidence=0.0:
                        ("close", {"used": True}) if k == tb.CANVAS_KEY else ("mensajeria:close", {"used": True}))
    monkeypatch.setattr(tb, "owner_still_open", lambda brief, owner: True)
    monkeypatch.setattr(da, "_open_now", lambda: ["agenda", "mensajeria"])
    monkeypatch.setattr(st, "close_target", lambda wid: wid.split(":")[0] if wid else "")
    closed = []
    da.complete_canvas({"x": 1}, tag_emit=lambda a, x: closed.append(x["id"]), emit=lambda *a, **k: None,
                       operator_text="close the calendar and the messages")
    assert sorted(closed) == ["agenda", "mensajeria"], closed
