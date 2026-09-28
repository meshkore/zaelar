"""A SILENT show of an EMPTY card gets its second pass (demo pass 2026-09-28, M1).

«how's apple stock doing today, show me the chart» → show_widget(markets), no symbol, no words, no verdict naming the
action → an empty chart, and «what about the last month» then failed. The empty card is the signal; the pass
(which judges what is due — node 2.89) is told what was actually done and decides.
"""
import asyncio

from nucleo.flash import card_commission as cc


def _run(monkeypatch, empty, got):
    import nucleo.flash.surface_ack as sa
    import nucleo.flash.act_repair as ar
    seen = {}

    async def call_for_promise(operator_text, said, wid, spec=None, **_kw):
        seen["said"] = said
        return got
    monkeypatch.setattr(sa, "nothing_to_show", lambda wid: empty)
    monkeypatch.setattr(ar, "call_for_promise", call_for_promise)
    applied = []
    ok = asyncio.run(cc.after_show({"widget_id": "markets"}, brief=None,
                                   operator_text="how's apple stock doing today, show me the chart", spoken_text="",
                                   spec=None, emit=lambda *a, **k: None, present=lambda *a, **k: None,
                                   apply_widget_data=lambda w, a, p: applied.append((w, a, p))))
    return ok, applied, seen


def test_a_silent_show_of_an_empty_card_gets_the_call(monkeypatch):
    ok, applied, seen = _run(monkeypatch, True, {"widget_id": "markets", "action": "show",
                                                 "payload": {"symbol": "AAPL", "range": "1d"}})
    assert ok and applied == [("markets", "show", {"symbol": "AAPL", "range": "1d"})]
    assert "VACÍA" in seen["said"], "the pass is told what was actually done"


def test_a_card_that_has_content_is_left_alone(monkeypatch):
    ok, applied, _ = _run(monkeypatch, False, {"widget_id": "markets", "action": "show", "payload": {"symbol": "X"}})
    assert not ok and not applied


def test_the_voice_call_site_no_longer_needs_words():
    import inspect
    from voice.engine.llm.providers import nucleo as prov
    assert 'if acted.get("widget_id") and not data_done["v"] and not clarify["msg"]:' in inspect.getsource(prov)
