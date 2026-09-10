"""The ◉ memory row says WHOSE fact it is showing — a slow recall is not a dead heart (2026-09-10).

Measured on the operator's own engine, minutes after a restart: the row read

    Memoria · CORAZÓN — «gpt-4.1-mini · 0 fallos — escribiendo por heurística»   (in red)

while the heart was distilling normally (pills 3285-3292 written in that same minute, served by the titular).
Two halves of one sentence, from two different places: «0 fallos» came from `mem_processor.status()`, and the
red came from `health_state["memory"]` — a key FOURTEEN writers share (the heart, REM, the retriever, the
embedding backend, the turn's recall budget). What had actually happened was a recall that did not close in
its 0.8 s budget, which fires on ~0.6 % of turns and held the light red for the full 600 s TTL each time. That
is why the operator saw it fail «una vez sí, una vez no» while the memory worked: an intermittent latency
warning wearing an outage's clothes.

The claim «escribiendo por heurística» is the expensive part. It is a statement about DATA LOSS — pills written
by the lossy fallback instead of the model — and reading it when it is not happening teaches the operator to
distrust a light that is usually right, which is the same as removing it.

So: the heart's own failure keeps the red and the narrative; anything else speaks in the words of whoever
recorded it, and a `degraded` record is amber, because a relay or a slow recall is a warning, not an outage.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from server import voice_api
from voice import health_state


def _memory_row(monkeypatch, *, heart: dict, recorded: tuple[str, str] | None):
    """The memory item as /api/status really builds it, with the heart and the shared light in a known state."""
    from nucleo import mem_processor

    monkeypatch.setattr(mem_processor, "status", lambda: heart)
    health_state.clear("memory")
    if recorded:
        health_state.record("memory", recorded[0], recorded[1])
    try:
        resp = asyncio.run(voice_api.status())
    finally:
        health_state.clear("memory")
    # The endpoint answers a JSONResponse: read the BODY the browser would get, so the assertions below are
    # about what the panel renders and not about an intermediate dict this test happened to reach for.
    payload = json.loads(bytes(resp.body).decode())
    rows = [it for it in payload["items"] if it["key"] == "memory"]
    assert rows, "the ◉ lost its memory row entirely"
    return rows[0]


_HEALTHY = {"model": "gpt-4.1-mini", "url": "https://api.openai.com/v1",
            "fail_streak": 0, "last_error": "", "last_ok_ts": 0.0, "degraded": False}
_RECALL_MISS = "el recall no cerró en 0.8s — el turno sigue SIN memoria durable"


def test_a_recall_that_missed_its_budget_is_amber_and_says_so(monkeypatch):
    """The measured case. Amber, in the recall's own words, and NOT accusing the heart of writing blind."""
    row = _memory_row(monkeypatch, heart=_HEALTHY, recorded=("degraded", _RECALL_MISS))
    assert row["state"] == "warn", f"a latency warning painted as an outage: {row}"
    assert "recall" in row["detail"], f"the row hides what actually happened: {row['detail']}"
    assert "heurística" not in row["detail"], (
        "the row claims the heart is writing through the lossy fallback while it is distilling fine — "
        f"this is the sentence the operator read for weeks: {row['detail']}"
    )


def test_the_hearts_own_outage_keeps_the_red_and_its_narrative(monkeypatch):
    """The counterweight: the fix must not buy honesty by going quiet on the failure the row exists for."""
    sick = {**_HEALTHY, "fail_streak": 3, "degraded": True}
    row = _memory_row(monkeypatch, heart=sick,
                      recorded=("outage", "3 fallos (gpt-4.1-mini @ …): timeout — heurística"))
    assert row["state"] == "error"
    assert "3 fallos" in row["detail"] and "heurística" in row["detail"], row["detail"]


def test_an_outage_that_is_not_the_hearts_is_red_in_its_own_words(monkeypatch):
    """REM running out of rungs IS an outage — red — but it is not the heart writing through the heuristic."""
    row = _memory_row(monkeypatch, heart=_HEALTHY,
                      recorded=("outage", "rem: sin proveedor (gpt-4.1-mini: timeout)"))
    assert row["state"] == "error"
    assert "rem: sin proveedor" in row["detail"], row["detail"]
    assert "0 fallos" not in row["detail"], (
        f"«0 fallos» inside an outage headline is the contradiction that gave the bug away: {row['detail']}"
    )


@pytest.mark.parametrize("streak", [0, 2])
def test_a_healthy_memory_shows_the_model_and_nothing_else(monkeypatch, streak):
    """Green when nothing is wrong; amber with the COUNT when the heart has stumbled but not given up."""
    row = _memory_row(monkeypatch, heart={**_HEALTHY, "fail_streak": streak}, recorded=None)
    if streak:
        assert row["state"] == "warn" and "2 fallo(s) recientes" in row["detail"]
    else:
        assert row["state"] == "ok" and row["detail"] == "gpt-4.1-mini"
