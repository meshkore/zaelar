"""A web search that shares NO word with his turn, on a turn the verdict reads surely as an order on a card, is dropped.

Demo pass 89 (2026-10-03), F2 «show me the part about proof of work»: beside the right `documento:goto` the model
emitted web_search «proveedores de internet fibra óptica Los Angeles», and the reply was composed from those results
(«the document is about internet providers in Los Angeles»).
"""
from __future__ import annotations

from nucleo.flash import direct_action as DA
from nucleo.flash import tool_executor_calls as TC


def _overlap(a, b):
    return len({w for w in a.lower().split() if len(w) > 3} & {w for w in b.lower().split() if len(w) > 3})


def test_a_search_with_nothing_of_his_words_on_a_sure_card_order_is_not_his(monkeypatch):
    monkeypatch.setattr(DA, "_action_sure", lambda brief, floor=0.8: True)
    assert not TC.a_search_is_his("proveedores de internet fibra óptica Los Angeles",
                                  "Show me the part about proof of work.", {"x": 1}, _overlap)


def test_a_search_that_shares_his_words_is_his(monkeypatch):
    monkeypatch.setattr(DA, "_action_sure", lambda brief, floor=0.8: True)
    assert TC.a_search_is_his("bitcoin proof of work explained", "Show me the part about proof of work.", {"x": 1},
                              _overlap)


def test_without_a_sure_card_order_any_search_is_his(monkeypatch):
    monkeypatch.setattr(DA, "_action_sure", lambda brief, floor=0.8: False)
    assert TC.a_search_is_his("Eiffel Tower height", "¿cuánto mide la torre?", {"x": 1}, _overlap)
