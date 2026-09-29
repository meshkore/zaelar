"""A data-op NAMED «close» over a sure close verdict is the card's own close (demo passes 36/42, 2026-09-29, E5).

«close my mail» — the model called the messaging card's `close` VIEW action (back to the chat list); the canvas
verdict read `close` sure; the card stayed on screen while the reply said the mail was closed, and the next order
found the mail still there."""
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]


def test_a_close_op_under_a_sure_close_verdict_is_the_card(monkeypatch):
    from nucleo.flash import direct_action as da
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "close")
    assert da.close_op_is_the_card(object(), "close")
    assert not da.close_op_is_the_card(object(), "unread"), "only an op named close"
    monkeypatch.setattr(da, "sure_canvas", lambda brief: "")
    assert not da.close_op_is_the_card(object(), "close"), "an unsure verdict keeps the card's own view op"


def test_the_data_op_door_closes_the_card_instead():
    prov = (ENGINE / "voice/engine/llm/providers/nucleo.py").read_text(encoding="utf-8")
    seg = prov.split("def _apply_widget_data(", 1)[1].split("_frag_why := ", 1)[0]
    assert "_direct_action.close_op_is_the_card(_brief, action_name)" in seg
    assert '_tag_emit("close", {"id": _show_target.close_target(wid)})' in seg
