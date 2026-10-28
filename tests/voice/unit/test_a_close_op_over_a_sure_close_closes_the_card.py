"""A data-op NAMED «close» over a sure close verdict is the card's own close (demo passes 36/42, 2026-09-29, E5).

«close my mail» — the model called the messaging card's `close` VIEW action (back to the chat list); the canvas
verdict read `close` sure; the card stayed on screen while the reply said the mail was closed, and the next order
found the mail still there."""
from tests import voice_turn_source as _vts
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]


def test_a_close_op_under_a_sure_close_verdict_is_the_card(monkeypatch):
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "close")
    assert da.close_op_is_the_card(object(), "close")
    assert not da.close_op_is_the_card(object(), "unread"), "only an op named close"
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "")
    assert not da.close_op_is_the_card(object(), "close"), "an unsure verdict keeps the card's own view op"


def test_the_data_op_door_closes_the_card_instead(monkeypatch):
    """The card door's GATE ladder reads it first, and the gate closes the card the licence names."""
    import inspect
    from nucleo.acts import card
    from nucleo.flash import direct_action as da, show_target as st, tool_executor_widget_calls as calls
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "close")
    monkeypatch.setattr(st, "close_target", lambda wid: f"{wid}::1")
    lic = card.licence({"brief": object(), "text": "close my mail"}, "mensajeria", "close", {}, at=card.GATE)
    assert (lic.verdict, lic.clause, lic.card) == (card.CLOSE, "close-is-the-card", "mensajeria::1")
    assert card._LADDER[card.GATE][0] is card._close_is_the_card, "before the fragment rule, as it was"
    gate = inspect.getsource(calls._apply_widget_data)
    assert '_tag_emit("close", {"id": _lic.card})' in gate
