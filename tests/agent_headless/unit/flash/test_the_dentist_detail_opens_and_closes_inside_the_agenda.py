"""The dentist's detail opens and closes INSIDE the agenda (agenda-everyday-edits ES, 2026-10-15).

  · «Ábreme la ficha del dentista, que quiero verla» — verdict `agenda:open_meeting` 0.99, the model only said «Voy a
    abrirla» (plus an invented tag). The verdict rung refused: `title` names a ROW, and a sentence is never stuffed
    into a selector. The row was right there — `refs.resolve` reads it from his sentence (V2-708) — so the rung
    now fills the selector with the one row his words name, and never with a sentence that names none.
  · «Vale, ya la puedes cerrar» — canvas=close 1.00 AND `agenda:close_meeting` 1.00, the model called
    `open_meeting`, and the short-close shortcut shut the whole AGENDA. A sure close that names another VIEW of the
    same card runs that view instead of the model's, in both channels; an unsure one keeps today's close.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.flash import card_close as CC
from nucleo.flash import direct_action as DA
from nucleo.flash import verdict_card as VC

SAID_OPEN = "Ábreme la ficha del dentista, que quiero verla"
SAID_CLOSE = "Vale, ya la puedes cerrar"


def test_the_rung_opens_the_one_row_his_sentence_names():
    from tests.brain.harness import Isolated
    with Isolated("es"):
        from memory import api as memapi
        from widgets.agenda import data as ag
        memapi.set_state({"open_widgets": ["agenda"]})
        ag.apply_action("add_meeting", {"title": "Dentista", "date": "2026-10-22", "startTime": "10:00",
                                        "endTime": "11:00"})
        ev = threading.Event()
        ev.set()
        brief = {"event": ev, "turn_id": "t", "open_ids": ["agenda"], "_call_id": "t", "result": {
            "screen_action": {"choice": "agenda:open_meeting", "confidence": 0.99},
            "canvas": {"choice": "show", "confidence": 1.0},
            "request_type": {"choice": "order", "confidence": 1.0},
            "wants_words": {"choice": "act", "confidence": 1.0}}}
        rung = DA.resolve(SAID_OPEN, brief=brief, operator_text=SAID_OPEN, model_words="Voy a abrirla.")
        assert (rung.get("action"), rung.get("payload")) == ("open_meeting", {"title": "Dentista"}), rung
        assert DA.named_row("agenda", "open_meeting", "ábreme la ficha del fontanero") == {}


@pytest.fixture
def verdict(monkeypatch):
    st = {"canvas": "close", "action": ("agenda", "close_meeting"), "conf": 1.0}
    monkeypatch.setattr(DA, "sure_canvas", lambda b: st["canvas"])
    monkeypatch.setattr(DA, "from_brief", lambda b: st["action"])
    monkeypatch.setattr(DA, "_action_sure", lambda b, floor=0.8: st["conf"] >= floor)
    monkeypatch.setattr(DA, "named_cards", lambda text: [])
    return st


def test_a_sure_close_of_the_detail_never_closes_the_agenda(verdict, monkeypatch):
    assert CC.data_close("agenda", "open_meeting", SAID_CLOSE, brief=object()) is False
    monkeypatch.setattr(DA, "resolve", lambda *a, **k: {"widget": "agenda", "action": "close_meeting", "payload": {}})
    assert VC.retarget(object(), "agenda", "open_meeting", {"title": "Dentista"}, SAID_CLOSE)[:2] == \
        ("agenda", "close_meeting")
    ran: list = []
    monkeypatch.setattr(DA, "complete", lambda *a, **k: ran.append(k.get("widget_id")) or "agenda:close_meeting")
    assert VC.takes_the_view(object(), "agenda", "open_meeting", operator_text=SAID_CLOSE, emit=lambda *a, **k: None,
                             present=None, apply_widget_data=None) and ran == ["agenda"]


def test_an_unsure_inner_verdict_keeps_the_close(verdict):
    verdict["conf"] = 0.6
    assert CC.data_close("agenda", "open_meeting", SAID_CLOSE, brief=object()) is True


def test_a_card_that_publishes_no_rows_never_gets_his_sentence_as_a_selector():
    """Demo pass 134, E3: `mensajeria` publishes no row index, `refs.resolve` handed the raw sentence back, and the
    rung filled `forward {from: «send the invoice to quinn…»}` — a forward with no recipient and no note."""
    from tests.brain.harness import Isolated
    with Isolated("en"):
        said = "send the invoice to quinn, tell him we're already trying inworld and he should book it"
        assert DA.named_row("mensajeria", "forward", said) == {}
