"""A round whose recalls were served by a degraded embeddings backend was not measured.

Established with the memory agent on 2026-08-21. A sandbox boot can log BOTH «embeddings in 'hash' —
SEMANTIC recall practically DISABLED» and, fifteen seconds later, «prewarm embeddings OK (ollama)».
Inside ONE process a degraded backend stays pinned for 300 s and nothing calls `reset()`, so a process
reporting `ollama` at prewarm cannot have resolved `hash` before it: the two lines are different
processes. The prewarm is the one that describes the process answering the turns — so the guard is to
READ IT, not to sleep five minutes before measuring.

Read from the EVENT and not from the log text: the backend arrives in a FIELD (`extra.model`), which a
change of log format cannot break, out of the same store every other mechanism reading here uses.
"""
from __future__ import annotations

import json
import sqlite3

from tests.use_cases.e2e.agent import status as S
from tests.use_cases.e2e.agent import verify as V


def _store(tmp_path, rows):
    """`rows` = [(kind, label, extra_dict)] in the shape `voice.observer.emit` writes."""
    db = tmp_path / "sandbox.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE events (topic TEXT, kind TEXT, label TEXT, payload TEXT, ts_ms INTEGER)")
    for i, (kind, label, extra) in enumerate(rows):
        con.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                    ("observer", kind, label, json.dumps({"extra": extra}), 1000 + i))
    con.commit()
    con.close()
    return db


def test_ollama_is_read_off_the_prewarm_event(tmp_path):
    db = _store(tmp_path, [("perf", "🔥 prewarm embed 5196ms", {"warm": "embed", "model": "ollama"})])
    out = V.embeddings_backend(db)
    assert out["backend"] == "ollama" and out["degraded"] is False and out["skipped"] is False


def test_a_hash_round_is_flagged_degraded(tmp_path):
    db = _store(tmp_path, [("perf", "🔥 prewarm embed 12ms", {"warm": "embed", "model": "hash"})])
    assert V.embeddings_backend(db)["degraded"] is True


def test_fastembed_counts_as_degraded_too(tmp_path):
    """T176: fastembed collapses with thousands of memories. It is not 'nearly ollama'."""
    db = _store(tmp_path, [("perf", "🔥 prewarm embed 2100ms", {"warm": "embed", "model": "fastembed"})])
    assert V.embeddings_backend(db)["degraded"] is True


def test_a_SKIPPED_prewarm_is_the_most_dangerous_case_and_is_caught(tmp_path):
    """The first version of this guard read «no OK line» as «nothing claimed» and graded the round
    normally. That is backwards: if the prewarm threw, the backend gets resolved by the FIRST RECALL —
    which is precisely when `hash` is likeliest. Absence of the OK is not evidence of health."""
    db = _store(tmp_path, [("perf", "🔥 prewarm embed 0ms — saltado: connection refused",
                            {"warm": "embed", "model": "?"})])
    out = V.embeddings_backend(db)
    assert out["skipped"] is True and out["degraded"] is True


def test_other_prewarms_are_not_mistaken_for_the_embeddings_one(tmp_path):
    """`_emit_prewarm` fires for the reranker and the browser too, on the same `perf` kind."""
    db = _store(tmp_path, [
        ("perf", "🔥 prewarm rerank 4495ms", {"warm": "rerank", "model": "jina-reranker-v2"}),
        ("perf", "🔥 prewarm embed 5196ms", {"warm": "embed", "model": "ollama"})])
    assert V.embeddings_backend(db)["backend"] == "ollama"


def test_no_prewarm_event_at_all_claims_NOTHING(tmp_path):
    """Silence must not be read as either health or breakage — only the absence of BOTH signals."""
    db = _store(tmp_path, [("perf", "🔥 prewarm rerank 4495ms", {"warm": "rerank", "model": "jina"})])
    assert V.embeddings_backend(db) == {}


def test_the_LAST_prewarm_wins(tmp_path):
    """A workspace reused across two boots holds both events; the round that ran is the later one."""
    db = _store(tmp_path, [("perf", "a", {"warm": "embed", "model": "hash"}),
                           ("perf", "b", {"warm": "embed", "model": "ollama"})])
    assert V.embeddings_backend(db)["backend"] == "ollama"


def test_an_unreadable_store_is_not_a_crash(tmp_path):
    assert V.embeddings_backend(tmp_path / "nope.db") == {}


def test_a_degraded_round_is_INFRA_not_FAIL():
    """It fails QUIET — an agent that could not recall by meaning looks exactly like one that forgot. A
    score filed from it is a product verdict earned by the harness's own environment."""
    row = {"run": {"transcript": ["a", "b", "c", "d"],
                   "mechanism_report": {"embeddings": {"backend": "hash", "degraded": True}}}}
    assert S._state(2, row) == "INFRA"


def test_a_healthy_round_is_graded_normally():
    row = {"run": {"transcript": ["a", "b", "c", "d"],
                   "mechanism_report": {"embeddings": {"backend": "ollama", "degraded": False}}}}
    assert S._state(2, row) != "INFRA"


def test_a_round_with_no_embeddings_reading_is_still_graded():
    """Older rounds and any boot that never emitted the event keep their verdict: an unmeasured confound
    is not evidence of one."""
    row = {"run": {"transcript": ["a", "b", "c", "d"], "mechanism_report": {}}}
    assert S._state(2, row) != "INFRA"
