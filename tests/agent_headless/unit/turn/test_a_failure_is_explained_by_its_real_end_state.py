"""A failure is explained by the errand's real end state, never by an invented one (node 2.458).

three-tasks-at-once (EN, 2026-10-11 02:58), t7: «the widget got built and then everything got wiped in a reset» —
`resets_during_round: 0`. The game had been DROPPED by a «no» the gate read off a sentence about monitors, and from
then on the state said nothing about it; asked, the model made a cause up. Later, the rebuilt game's worker died on
«the agent timed out» (every platform-game build of the last days hit the generator's cap) and the operator was told
only «I couldn't build the widget».

  · a declined confirmation is a FACT in the live state (like an expired one) until the errand is asked again;
  · the generator's timeout reaches him as its reason.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from nucleo import dispatch_confirm as dc

GAME = "Build a playable platform game widget, Super Mario style, with coins"


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.setattr(dc, "_PENDING_CONFIRM", {})
    monkeypatch.setattr(dc, "_EXPIRED_CONFIRM", {})
    monkeypatch.setattr(dc, "_DECLINED_CONFIRM", {})


def test_a_declined_errand_is_said_as_declined():
    dc._PENDING_CONFIRM["2"] = {"request": GAME, "kind": "code", "trusted": True, "context": {}, "sheet": "",
                                "ts": time.time(), "question": "Shall I?"}
    assert dc.resolve_confirm(False)["ok"] is False
    line = dc.confirm_line()
    assert "DESCARTADA" in line and "Super Mario" in line and "reinicio" in line, line


def test_asking_again_retires_the_old_no(monkeypatch):
    dc._DECLINED_CONFIRM["2"] = {"request": GAME, "declined_at": time.time()}
    dc.remember_offer(GAME + " and a higher jump", context={"kind": "code"}, question="Shall I?")
    assert not dc._DECLINED_CONFIRM
    assert "DESCARTADA" not in dc.confirm_line()


def test_a_declined_fact_ages_out():
    dc._DECLINED_CONFIRM["2"] = {"request": GAME, "declined_at": time.time() - dc._EXPIRED_MEMORY_S - 5}
    assert dc.confirm_line() == ""


def test_the_generator_timeout_is_said(monkeypatch):
    from widgets import generator
    from nucleo.agentes import code as _code
    from nucleo.workers import generator_session as gs
    monkeypatch.setattr(generator, "generate_widget", lambda *a, **k: {"ok": False, "error": "the agent timed out"})
    monkeypatch.setattr(_code, "widget_action", lambda req: ("create", ""))
    b = gs.GeneratorBackend()
    b._task_id = "8"
    asyncio.run(b._drive(GAME))
    results = []
    while not b._q.empty():
        ev = b._q.get_nowait()
        if ev.type == "result":
            results.append(ev.data.get("summary"))
    assert results and "se le acabó el tiempo" in results[0], results
