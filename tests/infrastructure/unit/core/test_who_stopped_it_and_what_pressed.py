"""Who stopped it, what the host looked like, what the worker was told (V2-837 G7/G8/G9).

Measured on one cloud session: the agent was stopped once and nothing said by what or from where; the «low memory»
worker notice and `homeostasis degraded` carried no number (only the self-watchdog had `free_ratio`); and the
composed research brief — the criteria the worker is held to — went only to the process log.

  G7  every `run` event and the session close carry `cause` (and `device` when a page sent it);
  G8  every `alert` and `homeostasis` event carries one `pressure` block, stamped at the observer's door;
  G9  the one door every brief is composed through emits `brief composed` with its declared fields.

Disarm: drop the `extra.setdefault("cause", …)` in `runstate._emit` → the run case goes red; drop the `pressure`
stamp in `observer.emit` → the alert case goes red; drop `_emit_brief` from `brief_door._compose_brief` → the brief
case goes red.
"""
from __future__ import annotations

import asyncio

import pytest


@pytest.fixture
def events(monkeypatch):
    from voice import observer
    got = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, text="", role="", extra=None: got.append(
        (kind, label, dict(extra or {}))))
    return got


@pytest.fixture
def runstate(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))   # never the operator's switch, even if a write slipped
    from nucleo import runstate as rs
    rs._reset_for_tests()
    monkeypatch.setattr(rs, "_persist", lambda value, src: rs._state.update({"value": value, "src": src}))
    from observability import identity
    monkeypatch.setattr(identity, "end_session", lambda *a, **k: {})
    monkeypatch.setattr(identity, "begin_session", lambda *a, **k: {})
    yield rs
    rs._reset_for_tests()


def test_a_stop_says_its_cause_and_device_and_a_bare_one_says_its_source(events, runstate):
    asyncio.run(runstate.stop("operator", cause="button", device="mobile:ab12"))
    (_, label, ex), = [e for e in events if e[0] == "run"]
    assert label == "stop" and ex["cause"] == "button" and ex["device"] == "mobile:ab12"
    assert ex["origin_dev"] == "mobile:ab12", "the screen that pressed it owns the row"
    events.clear()
    asyncio.run(runstate.start("energy_lease"))
    (_, label, ex), = [e for e in events if e[0] == "run"]
    assert label == "start" and ex["cause"] == "energy_lease" and "device" not in ex


def test_a_deferred_stop_keeps_who_asked_for_it(events, runstate):
    runstate.enter_inflight()
    asyncio.run(runstate.stop("operator", cause="client_state", device="desktop:1"))
    asyncio.run(runstate.exit_inflight())
    causes = [(lbl, ex["cause"]) for k, lbl, ex in events if k == "run"]
    assert causes == [("pausing", "client_state"), ("stop", "client_state")], causes


def test_the_page_sends_its_cause_and_the_route_passes_it(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nucleo import runstate as rs
    from server import run_api
    seen = {}

    async def _stop(src="operator", **kw):
        seen.update(kw, src=src)
        return {"ok": True}
    monkeypatch.setattr(rs, "stop", _stop)
    app = FastAPI()
    app.include_router(run_api.router)
    c = TestClient(app)
    assert c.post("/api/run/stop", json={"cause": "button", "dev": "desktop:9"}).json() == {"ok": True}
    assert seen == {"src": "operator", "cause": "button", "device": "desktop:9"}
    assert c.post("/api/run/stop").json() == {"ok": True}, "an older page that posts nothing still stops it"


def test_a_closed_voice_session_says_why(events):
    from voice.engine.pipeline import agent_events
    from voice import observer

    class _Reason:
        value = "participant_disconnected"

    class _Ev:
        reason, error = _Reason(), None
    nop = type("N", (), {"clear_speaker": staticmethod(lambda *a: None)})
    try:
        agent_events._on_close(_Ev(), _account_limits=None, _close_account_session=lambda *a, **k: None,
                               _emit=observer.emit, _proactive=nop, _speak=None, boot=None)
    except Exception:
        pass                                    # what runs after the row is not under test here
    (_, label, ex), = [e for e in events if e[0] == "session"]
    assert label == "session closed" and ex["cause"] == "participant_disconnected"


@pytest.mark.parametrize("kind", ["alert", "homeostasis"])
def test_every_pressure_event_carries_the_numbers(kind, monkeypatch):
    import bus
    from voice import observer
    got = []
    monkeypatch.setattr(bus, "emit_sync", lambda topic, ev, *a, **k: got.append(ev) if topic == "observer" else None)
    observer.emit(kind, f"v2-837 pressure probe {kind}", role="system", extra={"kind_diag": "envelope_late"})
    (ev,) = got
    p = ev.get("pressure") or {}
    assert {"rss_mb", "free_mb", "free_ratio", "browsers", "workers"} <= set(p), p
    assert p["free_mb"] > 0 and 0 < p["free_ratio"] <= 1


def test_the_composed_brief_is_on_the_record(events, monkeypatch):
    from nucleo import dispatch
    brief = {"goal": "ten used cars under 25k", "domain": "cars", "hard": ["price ≤ 25000 €"],
             "subjects": ["GLC 220d"], "breadth": {"min_candidates": 30}, "round": 1,
             "deliverable": {"widget": "results", "n_final": 10}}

    async def _compose(req, ctx):
        return brief
    monkeypatch.setattr(dispatch.research, "previous_round", lambda gk: None)
    monkeypatch.setattr(dispatch.research, "compose", _compose)
    assert asyncio.run(dispatch._compose_brief("find me cars", "", True, None, task_id="7")) is brief
    (_, label, ex), = [e for e in events if e[1] == "🧭 brief composed"]
    assert ex["how"] == "composed" and ex["n_final"] == 10 and ex["min_candidates"] == 30
    assert ex["hard"] == ["price ≤ 25000 €"] and ex["subjects"] == ["GLC 220d"] and ex["id"] == "7"

    async def _not_research(req, ctx):
        return None
    events.clear()
    monkeypatch.setattr(dispatch.research, "compose", _not_research)
    assert asyncio.run(dispatch._compose_brief("hello", "", True)) is None
    (_, _, ex), = events
    assert ex["how"] == "none", "a request the composer declined is recorded as such, not left silent"
