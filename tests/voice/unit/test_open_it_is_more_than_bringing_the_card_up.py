"""«Open it» is more than bringing the card up (node 2.189).

Demo pass 65, E2 (2026-09-30): after «did inworld send me something?» (answered by a read, the mail card closed),
«open it» brought the card up and said «Here you go.» — the receipt stayed shut. The card was closed when the brief
fired, so no verdict could name `open`; the words promised nothing; the card was not empty. An ORDER whose words name
no card had its card chosen by context, which is a guess at the object, not the act — so the second pass now runs,
with the card (and its digest: «what you last found… `open` with nothing opens it») in front.
"""
import asyncio

from nucleo.flash import card_commission as cc
from nucleo.flash import direct_action as da


def _run(monkeypatch, text, order=True):
    import nucleo.flash.surface_ack as sa
    import nucleo.flash.act_repair as ar
    monkeypatch.setattr(sa, "nothing_to_show", lambda wid: False)
    monkeypatch.setattr(da, "reads_as_order", lambda brief: order)
    monkeypatch.setattr(da, "names_an_order", lambda brief, sure=0.0: False)
    monkeypatch.setattr(cc, "named_or_catalogue", lambda brief, text, **k: "")
    asked = []

    async def call_for_promise(operator_text, said, wid, spec=None, **_kw):
        asked.append(wid)
        return {"widget_id": "mensajeria", "action": "open", "payload": {}}
    monkeypatch.setattr(ar, "call_for_promise", call_for_promise)
    applied = []
    ok = asyncio.run(cc.after_show({"widget_id": "mensajeria"}, brief={"x": 1}, operator_text=text,
                                   spoken_text="Here you go.", spec=None, emit=lambda *a, **k: None,
                                   present=lambda *a, **k: None,
                                   apply_widget_data=lambda w, a, p: applied.append((w, a, p))))
    return ok, asked, applied


def test_an_order_naming_no_card_gets_its_pass(monkeypatch):
    ok, asked, applied = _run(monkeypatch, "open it")
    assert asked == ["mensajeria"]
    # a bare `open` is the card's «open the one it last found» (widgets/mensajeria `last_found`), not a plain show
    assert ok and applied == [("mensajeria", "open", {})]


def test_a_sentence_that_names_its_card_is_left_alone(monkeypatch):
    ok, asked, applied = _run(monkeypatch, "show me my messages")
    assert asked == [] and not ok


def test_a_remark_is_left_alone(monkeypatch):
    ok, asked, applied = _run(monkeypatch, "nice", order=False)
    assert asked == [] and not ok
