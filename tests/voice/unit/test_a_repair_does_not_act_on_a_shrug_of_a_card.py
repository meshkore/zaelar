#
# test_a_repair_does_not_act_on_a_shrug_of_a_card.py — demo pass 35 (2026-09-29), B1.
#
# «find me the wallpaper cosmic eye in the sky by tyler young» — the model called nothing and said «Done». The
# repair asked the catalogue which card the order was for; it read `navegador` at 0.63, above the classifier's
# «not a shrug» (0.5), and the repair ran a browser search in the model's place. That card sat on the canvas
# until the end of the demo, one of four. A repair acts on a card nobody has seen yet, so it needs a card named
# with conviction — every late read that named the right card across the recorded passes was at 0.74 or more.
#
import threading

import pytest

from nucleo import jev
from nucleo.flash import build_decision, card_commission as cc, turn_brief as tb


@pytest.fixture
def ask(monkeypatch):
    monkeypatch.setattr(build_decision, "named_card", lambda brief: "")
    monkeypatch.setattr(tb, "catalog_question", lambda: {"instructions": "i", "criteria": {"navegador": "n"}})
    ev = threading.Event(); ev.set()
    brief = {"event": ev, "turn_id": "t", "open_ids": ["results"],
             "result": {tb.TARGET_KEY: {"choice": "none", "confidence": 0.95}}}

    def _ask(card, conf):
        monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: {"choice": card, "confidence": conf})
        return cc.named_or_catalogue(brief, "find me the wallpaper cosmic eye in the sky")
    return _ask


def test_a_card_read_at_063_is_not_acted_on(ask):
    assert ask("navegador", 0.63) == ""


def test_a_card_read_with_conviction_still_is(ask):
    assert ask("mensajeria", 0.99) == "mensajeria"
    assert ask("agenda", 0.74) == "agenda"
