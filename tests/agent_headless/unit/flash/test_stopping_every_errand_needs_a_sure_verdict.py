"""Stopping EVERY running errand needs the brief's sure `stop_all`, never a word in his sentence (refactor2710-06 T-03).

Killing several distinct errands is irreversible. The brief's `stop_errand` question now answers `stop_all`; only a
sure one (≥ VETO) stops them all. Anything less stops the one his words name, or asks which — fail-closed: «para
todo» with no verdict no longer kills every errand on a word.
"""
from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from nucleo.flash import tool_executor_calls as calls
from nucleo.request import stop as sd


def _brief(choice: str, conf: float) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-stop", "open_ids": [], "result": {sd.KEY: {"choice": choice, "confidence": conf}}}


@pytest.fixture
def two_errands(monkeypatch):
    from nucleo import dispatch, reset
    cancelled = []
    monkeypatch.setattr(dispatch, "pending_summaries", lambda: [{"request": "un informe de coches"},
                                                                {"request": "un monitor de segunda mano"}])
    monkeypatch.setattr(dispatch, "resolve_sessions", lambda text: [])
    monkeypatch.setattr(dispatch, "cancel_soon", lambda which: cancelled.append(which) or [1, 2])
    monkeypatch.setattr(reset, "abandon_work_soon", lambda source="": None)

    def stop(brief, text="para todo"):
        clarify, acted = {"msg": ""}, {"v": None}
        calls._t_stop_worker(args={"which": "todo"}, _norm_nfkd=str.lower,
                             _say=lambda: SimpleNamespace(stop_which_worker="Which one?", stop_doubt="Stop it?"),
                             _says_stop=lambda t: True, clarify=clarify, emit=lambda *a, **k: None, text=text,
                             worker_acted=acted, brief=brief)
        return cancelled, clarify["msg"]
    return stop


def test_a_sure_stop_all_stops_every_errand(two_errands):
    cancelled, ask = two_errands(_brief(sd.STOP_ALL, 0.93))
    assert cancelled == ["todo"] and not ask


def test_an_unsure_stop_all_or_no_verdict_asks_which(two_errands):
    cancelled, ask = two_errands(_brief(sd.STOP_ALL, 0.6))
    assert not cancelled and ask == "Which one?"
    cancelled, ask = two_errands(None, text="para todo, para todas las tareas")
    assert not cancelled and ask == "Which one?", "a word in his sentence is not the verdict"
