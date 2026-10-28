"""A messaging channel he names while nothing is linked reaches the prompt with its state (dictate-a-reply EN, 2026-10-15).

«Reply to Marta on WhatsApp…» with no channel linked: the prompt carried no messaging line at all (it is gated on a
platform being enabled), and the model answered «I can't find any chat from Marta» — true, and with no way out: not
a word of WhatsApp being unlinked nor of ⚙ Connectors. The line now rides on his naming the channel, so an idle turn
pays nothing (the composed prompt's ceilings stay where they were).
"""
from __future__ import annotations


def _nothing_linked(monkeypatch):
    from connectors.telegram import service as tg
    from connectors.whatsapp import service as wa
    monkeypatch.setattr(wa, "enabled", lambda: False)
    monkeypatch.setattr(tg, "enabled", lambda: False)


def test_naming_whatsapp_with_nothing_linked_brings_its_state_and_the_way_to_link_it(monkeypatch):
    _nothing_linked(monkeypatch)
    from nucleo.turn.prompt import catalogs as cb
    out = cb.connector_facts(set(), "Reply to Marta on WhatsApp that I'll be there at nine")
    assert "WhatsApp: SIN conectar" in out and "show_panel(panel='conectores'" in out, out[:400]


def test_an_idle_turn_pays_nothing_for_it(monkeypatch):
    _nothing_linked(monkeypatch)
    from nucleo.turn.prompt import catalogs as cb
    assert "CONECTORES activos" not in cb.connector_facts(set(), "what do I have tomorrow?")
