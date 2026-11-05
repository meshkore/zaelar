"""C8 — «stop» while a task runs: the row is `cancelled` by `circuit.settle`, and the worker acts no more
(V2-851 §3b, §9)."""
from __future__ import annotations

import time

import pytest

from .probe import WRITER_SETTLE, bridge_acts, brief, payload
from .script import ERRAND, LANGS, STOP, visible_rows_since, wait_worker


@pytest.mark.parametrize("errand", ["hotel", "flights"])
@pytest.mark.parametrize("lang", LANGS)
def test_c08_stop_cancels_through_settle(probe_for, check, lang, errand, rep):
    p = probe_for(lang)
    turn = p.say(ERRAND[lang][errand])
    ws = wait_worker(p, turn.since)
    check.that("the task was running", bool(ws), "no worker_start")
    rows = visible_rows_since(p, turn.t0)
    row = rows[-1] if rows else {}
    time.sleep(15)
    stop = p.say(STOP[lang])
    time.sleep(25)
    states = [payload(e) for e in p.task_states_since(stop.since, row.get("id", ""))]
    check.that("cancelled by settle", any(s.get("state") == "cancelled" and s.get("writer") == WRITER_SETTLE
                                          for s in states), {"row": brief(row), "task_state": states})
    check.that("the row is cancelled", (p.row(row.get("id", "")) or {}).get("state") == "cancelled",
               brief(p.row(row.get("id", "")) or {}))
    acts = bridge_acts(p.events_since(stop.since), str((payload(ws or {}) or {}).get("id") or ""),
                       payload(ws or {}).get("trace", ""))
    check.that("no bridge act after the stop", not acts, [brief(a) for a in acts])
    check.done(expected_red=check.expected)
