"""A show the canvas door refuses leaves a row, never silence; a show the verdict owes is made (refactor2710-99, J009).

Journey J009 (2026-10-28): «Vale, pues muéstramelo y déjalo abierto.» — the model answered «te dejo abierta la tarjeta
del tiempo» and called nothing, the sure `canvas = show` verdict named the card, and nothing opened: the show backstop
ran only when the model had called a spurious tool. The verdict now completes a show the model only promised (bank case
`journey-j009-show-it-and-leave-it-open`). And whatever the door refuses — the arbiter, an errand's step, a show with
no declared reason — is a row on the timeline (`arbiter` / `step` / `widget` «presentación suprimida»).

Disarm: make `canvas_verdict.show_owed` return False and the first test goes red.
"""
from __future__ import annotations

import threading


def _brief(**answers):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t", "open_ids": [],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in answers.items()}}


def test_a_sure_show_verdict_owes_the_card_it_names():
    from nucleo.flash import direct_action  # noqa: F401 — loads canvas_verdict the way the turn does (they import each other)
    from nucleo.acts import canvas_verdict
    assert canvas_verdict.show_owed(_brief(canvas=("show", 0.95)), "search")
    assert not canvas_verdict.show_owed(_brief(canvas=("show", 0.6)), "search"), "an unsure verdict owes nothing"
    assert not canvas_verdict.show_owed(_brief(canvas=("show", 0.95)), ""), "no card, nothing to show"
    assert not canvas_verdict.show_owed(_brief(canvas=("close", 0.95)), "search")


def test_every_refusal_of_the_door_is_a_row(monkeypatch):
    from voice import observer
    rows = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **kw: rows.append((kind, label)))
    from nucleo.acts import canvas
    from nucleo.flash import canvas_visibility as cvis
    assert canvas.apply("show", "search", src="flash", text="hola", request={"text": "hola"}) is False
    assert any(k == "arbiter" for k, _ in rows), "an arbiter veto is said"
    rows.clear()
    assert cvis.present("search", reason="", src="flash") is False
    assert ("widget", "🚫 presentación suprimida") in rows, "a show with no declared reason is said"
