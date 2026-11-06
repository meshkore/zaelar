"""The pulse leaves its beat on the observer timeline (capture gaps, 2026-11-06).

`loop.tick` and the crons that fire (`loop.scheduled_fired`) went to the bus of in-process signals only: neither the
engine's ◷ viewer nor the operator console had an event per cycle, and the cycles were reconstructed by grouping the widgets'
own `background · tick` rows. Now `nucleo/pulse/signals._emit` mirrors every `loop.*` signal as kind `pulse`: a cron
that fires is `pulse · scheduled_fired` with the job's id and name (his prompt as a bounded text, never a field), a cycle that
took real time is `pulse · tick` with its ms, and the quiet seconds are summed into one `pulse · beat` per
`BEAT_TICKS` cycles — one row per idle second would be the STTMetrics flood again.

Disarm: drop the `_mirror` call from `_emit` (or the `ms` from the loop's tick payload) → red.
"""
from __future__ import annotations

import asyncio

import pytest

from nucleo.pulse import loop as nloop
from nucleo.pulse import signals


@pytest.fixture
def rows(monkeypatch):
    out: list[dict] = []
    import voice.observer as obs

    def fake_emit(kind, label, text="", role="", extra=None):
        out.append({"kind": kind, "label": label, "text": text, "role": role, **(extra or {})})
    monkeypatch.setattr(obs, "emit", fake_emit)
    monkeypatch.setattr(signals, "TICK_MIN_MS", 250)
    monkeypatch.setattr(signals, "BEAT_TICKS", 60)
    signals._period.update(ticks=0, ms=0, max=0, slow=0)
    return out


def test_a_cron_that_fires_is_one_pulse_row_with_its_words_bounded(rows):
    signals._emit("loop.scheduled_fired", {"id": "job-7", "name": "medicación", "prompt": "toma la pastilla " * 40})
    assert len(rows) == 1
    r = rows[0]
    assert (r["kind"], r["label"], r["id"], r["name"]) == ("pulse", "scheduled_fired", "job-7", "medicación")
    assert r["text"].startswith("toma la pastilla") and len(r["text"]) <= signals._TEXT_MAX
    assert "prompt" not in r, "his words travel as the row's bounded text, never as a field"


def test_the_other_loop_signals_are_mirrored_too_and_nothing_else_is(rows):
    signals._emit("loop.spark", {"text": "ideas"})
    signals._emit("loop.consolidated", {"deduped": 3, "evicted": 0, "promoted": None})
    signals._emit("worker.say", {"text": "not a loop signal"})
    assert [r["label"] for r in rows] == ["spark", "consolidated"]
    assert rows[0]["text"] == "ideas" and rows[1]["deduped"] == 3 and "promoted" not in rows[1]


def test_a_quick_tick_is_summed_into_a_beat_and_a_slow_one_stands_alone(rows):
    for n in range(1, 60):
        signals._emit("loop.tick", {"ts": 0.0, "n": n, "ms": 4})
    assert rows == [], "59 quiet cycles leave no row of their own"
    signals._emit("loop.tick", {"ts": 0.0, "n": 60, "ms": 900})
    assert [r["label"] for r in rows] == ["tick", "beat"]
    tick, beat = rows
    assert tick["ms"] == 900 and tick["n"] == 60
    assert beat["ticks"] == 60 and beat["max_ms"] == 900 and beat["slow"] == 1 and beat["avg_ms"] == round((59 * 4 + 900) / 60)
    signals._emit("loop.tick", {"ts": 0.0, "n": 61, "ms": 3})
    assert len(rows) == 2, "the period starts again after a beat"


def test_the_loop_measures_each_cycle_and_the_signal_carries_its_ms(monkeypatch):
    seen: list[tuple[str, dict]] = []
    lp = nloop.OrchestratorLoop()
    for name in ("_supervise_workers", "_supervise_confirms", "_supervise_harness", "_supervise_events",
                 "_supervise_errands", "_supervise_stale_flows", "_fire_due", "_report_wake", "_maybe_spark",
                 "_maybe_consolidate"):
        async def step(now):
            await asyncio.sleep(0)
        monkeypatch.setattr(lp, name, step)
    monkeypatch.setattr(lp, "_supervise_memory", lambda now: None)
    monkeypatch.setattr(lp, "_close_idle_session", lambda: None)
    monkeypatch.setattr(lp, "_maybe_idle_stop", lambda now: None)
    monkeypatch.setattr(nloop, "_emit", lambda topic, payload=None: seen.append((topic, payload or {})))
    asyncio.run(lp.tick())
    (topic, payload), = [s for s in seen if s[0] == "loop.tick"]
    assert payload["n"] == 1 and isinstance(payload["ms"], int) and payload["ms"] >= 0


def test_a_record_that_fails_never_stops_the_beat(monkeypatch):
    import voice.observer as obs

    def boom(*a, **k):
        raise RuntimeError("disk full")
    monkeypatch.setattr(obs, "emit", boom)
    signals._emit("loop.scheduled_fired", {"id": "x", "name": "y"})      # must not raise
