"""Node 2.463 — the refusal is parked at the one seam both channels share (`data_ops.corrected_retry`): a refusal the
repair could not correct stays parked for his next turn; one the repair landed is forgotten.

Video-queue use case, ES round of 2026-10-11 (engine 3.36+d6f4a99f): the round ran on the TEXT channel, where
`data_ops.remember_refusal` is never written (it lives in the voice executor's seal) — so a memory installed there
would have been a rule on one of two branches.
"""
from __future__ import annotations

import asyncio
import pathlib

from nucleo.flash import act_repair as _ar
from nucleo.flash import data_ops as _do
from nucleo.flash import parked_refusal as _parked

_ENGINE = pathlib.Path(__file__).resolve().parents[4]
REFUSED = {"ok": False, "error": "missing_position", "message": "¿A qué posición de la cola lo muevo?"}


def _retry(monkeypatch, fix, landed):
    async def _no_fix(*_a, **_k):
        return fix
    monkeypatch.setattr(_ar, "call_for_refusal", _no_fix)

    async def _dispatch(_w, _a, _p):
        return landed
    return asyncio.run(_do.corrected_retry("youtube", "move", {"item": "2"}, REFUSED, "ponlo el primero", _dispatch))


def test_a_refusal_the_repair_could_not_correct_stays_parked(monkeypatch):
    _parked.forget()
    assert _retry(monkeypatch, None, {}) is None
    assert _parked.last("youtube", "move") == {"action": "move", "payload": {"item": "2"},
                                               "message": REFUSED["message"]}


def test_a_corrected_call_that_landed_is_forgotten(monkeypatch):
    _parked.forget()
    out = _retry(monkeypatch, {"payload": {"item": "2", "to": 1}}, {"ok": True, "position": 1})
    assert out and out[0] == {"item": "2", "to": 1}
    assert _parked.last("youtube", "move") is None


def test_a_corrected_call_refused_again_is_the_one_parked(monkeypatch):
    _parked.forget()
    again = {"ok": False, "error": "bad_position", "message": "No entiendo a qué posición moverlo."}
    _retry(monkeypatch, {"payload": {"item": "2", "to": "la luna"}}, again)
    rec = _parked.last("youtube", "move")
    assert rec and rec["payload"] == {"item": "2", "to": "la luna"} and rec["message"] == again["message"]


def test_the_turn_passes_a_refusal_through_that_seam():
    voice = (_ENGINE / "nucleo/flash/data_ops.py").read_text(encoding="utf-8")
    assert "await corrected_retry(wid, action_name, payload, res, text, _run" in voice
    assert voice.count("_parked.remember(") == 2          # the refusal, and the corrected call's own result
