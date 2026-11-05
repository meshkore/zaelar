"""C10 — the worker process killed mid-task: the row says where it was, and what it produced so far is kept
(V2-851 §3, §9)."""
from __future__ import annotations

import time

import pytest

from .probe import Infra, Probe, brief
from .script import ERRAND, LANGS, visible_rows_since, wait_worker


@pytest.mark.parametrize("lang", LANGS)
def test_c10_a_killed_worker_leaves_its_place(own_engine, check, lang, rep):
    p = Probe(own_engine(lang), session="bat-c10")
    turn = p.say(ERRAND[lang]["hotel"])
    if not wait_worker(p, turn.since):
        raise Infra("no worker started — nothing to kill")
    time.sleep(30)
    rows = visible_rows_since(p, turn.t0)
    row = rows[-1] if rows else {}
    procs = p.worker_processes(row.get("id", "-"))
    if not procs:
        raise Infra(f"no worker process found for {row.get('id')}")
    for pr in procs:
        pr.kill()
    time.sleep(30)
    after = p.row(row["id"]) or {}
    check.that("the row says where it was", bool(after.get("phase")) and bool(after.get("waiting_for"))
               and after.get("state") not in ("done", "cancelled"), brief(after))
    check.that("the artefacts so far are kept", bool(p.artifacts(row["id"])), p.artifacts(row["id"]))
    check.done(expected_red=check.expected)
