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
    import pathlib
    from nucleo.flash import direct_action as da
    assert da._says_the_name("close the calendar and the messages", "mensajeria")
    assert not da._says_the_name("close the chat", "mensajeria")
    src = (pathlib.Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py").read_text("utf-8")
    i = src.index("close ignorado — la orden es una acción DENTRO de la tarjeta")
    guard = src[src.rindex("if (action", 0, i):i]
    assert "_direct_action._says_the_name(_bnotes.operator_half(text)" in guard
