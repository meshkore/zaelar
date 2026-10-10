"""The delivery backstop never announces the same row twice in one errand (V2-781, search-buy-used-car).

Turn 0 glued «Motor De Coche VW Phaeton…», «Radio de coche BMW X5…» to a waiting reply; he called them junk twice;
by turn 8 the conversation window had pruned that reply, the «already said» test no longer saw them, and the same
batch went out again as «Actually, there are already candidates…». What the backstop said is remembered by the
backstop, not borrowed from a window that forgets.
"""
from nucleo.flash import delivery, live_blocks

ROWS = ["Motor De Coche VW Phaeton Audi — 450 €", "Radio de coche BMW X5 (E70) — 120 €", "Dacia Sandero 2019 — 7.900 €"]


def _wire(monkeypatch, rows):
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("coche usado barato", list(rows)))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    delivery.forget_announced()


def test_a_row_once_announced_is_not_announced_again_after_the_window_forgets(monkeypatch):
    _wire(monkeypatch, ROWS[:2])
    first = delivery.apply_to_reply("Sigo con ello.", [])
    assert "Phaeton" in first
    again = delivery.apply_to_reply("Sigo buscando.", [])          # the window no longer holds turn 0
    assert "Phaeton" not in again and "BMW X5" not in again


def test_a_new_row_is_still_announced(monkeypatch):
    _wire(monkeypatch, ROWS[:2])
    delivery.apply_to_reply("Sigo con ello.", [])
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("coche usado barato", list(ROWS)))
    assert "Dacia Sandero" in delivery.apply_to_reply("Sigo buscando.", [])
