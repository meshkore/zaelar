"""Node 2.692 — the text channel's reply passes the row-claims guard and the owed-notice delivery
(`delivery.apply_to_reply`), after the amount gate and before the row check and the delivery backstops.

search-buy-phone__us (2026-10-14): the reply «Yes — the iPhone 17 256GB at 699 is still available» left the turn as
written. Through `apply_to_reply` the claim is said as not verified, with the sheet read from a temporary store.

Disarm: remove the `_claims.guard(...)` call from `apply_to_reply` → the first test goes red; remove
`_note.deliver(...)` → the second goes red.
"""
from __future__ import annotations

import pytest

from nucleo.flash import claim_backing as B
from nucleo.flash import delivery

from ._claim_scene import SKI_NOTICE_TURN, SKI_SKIPPED

ROW = {"title": "iphone 17 256gb", "price": "699",
       "facts": [{"label": "Disponible para compra ahora (en stock o con plazo de entrega indicado)", "value": "?"}]}


@pytest.fixture
def sheet(monkeypatch, tmp_path):
    from widgets import store
    from widgets.results import data
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    store.save(data.sheet_key(""), {"title": "iPhone 17", "items": [ROW], "criteria": {"hard": [ROW["facts"][0]["label"]]}})
    monkeypatch.setattr(B, "in_errand", lambda: True)
    monkeypatch.setattr(B, "goals", lambda: "")


def test_an_unbacked_claim_leaves_the_text_channel_as_not_verified(sheet, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    out = delivery.apply_to_reply("Yes — the iPhone 17 256GB at 699 is still available.",
                                  [{"role": "user", "content": "Is the 699 still available?"}],
                                  heard_now="Is the 699 still available?")
    assert "is still available" not in out and "verified for «iphone 17 256gb»: available" in out


def test_a_pushed_finding_the_reply_skipped_leaves_with_it(sheet, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    out = delivery.apply_to_reply(SKI_SKIPPED, [{"role": "user", "content": SKI_NOTICE_TURN}], heard_now="re-run it")
    assert "Nordica Nemesis 161 with Dynafit bindings in Oakland for $150" in out
