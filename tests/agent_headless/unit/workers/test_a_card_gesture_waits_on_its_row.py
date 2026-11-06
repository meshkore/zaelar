"""Deleting or restoring a card, connecting a cluster or a held cluster send waits on a ROW (V2-857 phase 3, the
operator's decision 2026-11-06: «sí, tarea con fila»).

These four used to wait in this process's memory (`widgets.confirm._PENDING`) and their yes was read by a word list
before the brief: a restart or a barge-in lost the question. Now each is asked through the one asker
(`consent_ask.ask_consent(kind=)`), and his yes — the brief's pick `#0`, the card's button, or his words — runs the
same door the in-memory resolver ran (`consent_ask.ACTS`), once; a no ends the row.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

from nucleo.request import consent_ask, inline_ask


@pytest.fixture
def doors(monkeypatch):
    from nucleo import circuit
    from nucleo.circuit import ledger
    from nucleo.cli import worker_api  # noqa: F401 — the package first: its answer module imports it back
    from nucleo.cli import worker_api_answer
    from widgets import lifecycle
    ran, settled = [], []

    async def _del(wid, src="system"):
        ran.append(("delete", wid)); return {"ok": True}

    async def _res(wid, src="system"):
        ran.append(("restore", wid)); return {"ok": True}
    monkeypatch.setattr(lifecycle, "delete_widget", _del)
    monkeypatch.setattr(lifecycle, "restore_widget", _res)
    monkeypatch.setattr(circuit, "settle", lambda **k: settled.append(k))
    monkeypatch.setattr(ledger, "resumed", lambda uid: None)
    monkeypatch.setattr(worker_api_answer, "_says_yes", lambda q, t: t.lower().startswith(("sí", "si", "yes", "vale")))
    inline_ask._TAKEN.clear()
    return ran, settled


def _entry(kind, wid="agenda", n=1):
    return {"ask_id": f"r{n}-q", "question": "¿Seguro?", "inline": True,
            "retained": {"widget": wid, "action": kind, "payload": {}, "kind": kind, "op": {}}}


@pytest.mark.parametrize("kind,yes", [("delete", "sí, bórrala"), ("restore", "yes, restore it")])
def test_his_yes_runs_the_gesture_once(doors, kind, yes):
    ran, settled = doors
    e = _entry(kind)
    assert asyncio.run(inline_ask.rerun("r1", e, yes))["ok"] is True
    assert asyncio.run(inline_ask.rerun("r1", e, yes)) is None            # a second reader of the same yes: nothing
    assert ran == [(kind, "agenda")] and settled[-1]["state"] == "done"


def test_the_brief_pick_is_the_yes(doors):
    ran, _ = doors
    asyncio.run(inline_ask.rerun("r2", _entry("delete", n=2), "", choice=0))
    assert ran == [("delete", "agenda")]


def test_a_no_ends_the_row_and_runs_nothing(doors):
    ran, settled = doors
    assert asyncio.run(inline_ask.rerun("r3", _entry("delete", n=3), "no, déjala"))["ok"] is False
    assert not ran and settled[-1]["state"] == "cancelled"


def test_disarmed_a_gesture_with_no_act_runs_nothing(doors, monkeypatch):
    ran, _ = doors
    monkeypatch.setattr(consent_ask, "ACTS", {})
    asyncio.run(inline_ask.rerun("r4", _entry("delete", n=4), "sí"))
    assert not ran


def test_every_gesture_asks_on_a_row_first():
    from connectors.meshkore import send_gate
    from nucleo.flash import tool_executor_widget as txw
    src = inspect.getsource(txw.build)
    for kind in ('"delete"', '"restore"', '"cluster"'):
        assert "_ask_kind_on_its_row(" in src and kind in src
    assert "consent_ask" in inspect.getsource(send_gate.gate)
    assert set(consent_ask.ACTS) == {"delete", "restore", "cluster"}


def test_the_browser_click_reads_his_yes_through_the_one_reader():
    from widgets.navegador.owner import browser_steps
    src = inspect.getsource(browser_steps)
    assert "says_yes(" in src and '"adelante", "hazlo"' not in src
