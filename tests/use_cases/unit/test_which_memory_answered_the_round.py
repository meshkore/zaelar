"""A round whose recalls were served by a degraded embeddings backend was not measured.

Established with the memory agent on 2026-08-21. A sandbox boot can log BOTH «embeddings en 'hash' —
recall SEMÁNTICO prácticamente DESACTIVADO» and, fifteen seconds later, «prewarm embeddings OK (ollama)».
Inside ONE process a degraded backend stays pinned for 300 s and nothing calls `reset()`, so a process
reporting `ollama` at prewarm cannot have resolved `hash` before it: the two lines are different
processes. The prewarm line is the one that describes the process answering the turns — so the guard is
to READ IT, not to sleep five minutes before measuring.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import status as S
from tests.use_cases.e2e.agent import verify as V


def _log(tmp_path, text: str):
    ws = tmp_path / "memory" / "_data"
    ws.mkdir(parents=True)
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "sandbox-engine.log").write_text(text, encoding="utf-8")
    db = ws / "sandbox.db"
    db.write_text("", encoding="utf-8")
    return db


def test_ollama_is_read_off_the_prewarm_line(tmp_path):
    db = _log(tmp_path, "10:12:02 | INFO | prewarm embeddings OK (ollama, 5196ms) — recall listo en frío\n")
    out = V.embeddings_backend(db)
    assert out["backend"] == "ollama" and out["degraded"] is False


def test_the_contradictory_warning_does_NOT_win(tmp_path):
    """The `⚠️` line has no timestamp because it comes from stdlib logging in some other process that
    inherited stderr. Reading it as the round's backend would throw away good rounds."""
    db = _log(tmp_path, (
        "⚠️ memoria: embeddings en 'hash' (Ollama/embeddinggemma NO disponible) — recall SEMÁNTICO "
        "prácticamente DESACTIVADO (solo FTS léxico).\n"
        "10:12:02 | INFO | prewarm embeddings OK (ollama, 5196ms) — recall listo en frío\n"))
    assert V.embeddings_backend(db)["backend"] == "ollama"


def test_a_hash_round_is_flagged_degraded(tmp_path):
    db = _log(tmp_path, "10:12:02 | INFO | prewarm embeddings OK (hash, 12ms) — recall listo en frío\n")
    assert V.embeddings_backend(db)["degraded"] is True


def test_fastembed_counts_as_degraded_too(tmp_path):
    """T176: fastembed collapses with thousands of memories. It is not 'nearly ollama'."""
    db = _log(tmp_path, "10:12:02 | INFO | prewarm embeddings OK (fastembed, 2100ms) —\n")
    assert V.embeddings_backend(db)["degraded"] is True


def test_no_line_claims_NOTHING(tmp_path):
    """Silence must not be read as either health or breakage: an absent line is an absent measurement."""
    db = _log(tmp_path, "10:12:02 | INFO | algo completamente distinto\n")
    assert V.embeddings_backend(db) == {}


def test_the_LAST_prewarm_wins(tmp_path):
    """A workspace reused across two boots holds both lines; the round that ran is the later one."""
    db = _log(tmp_path, ("prewarm embeddings OK (hash, 9ms) —\n"
                         "prewarm embeddings OK (ollama, 5196ms) —\n"))
    assert V.embeddings_backend(db)["backend"] == "ollama"


def test_a_degraded_round_is_INFRA_not_FAIL(tmp_path):
    """It fails QUIET — an agent that could not recall by meaning looks exactly like one that forgot. A
    score filed from it is a product verdict earned by the harness's own environment."""
    row = {"run": {"transcript": ["a", "b", "c", "d"],
                   "mechanism_report": {"embeddings": {"backend": "hash", "degraded": True}}}}
    assert S._state(2, row) == "INFRA"


def test_a_healthy_round_is_graded_normally(tmp_path):
    row = {"run": {"transcript": ["a", "b", "c", "d"],
                   "mechanism_report": {"embeddings": {"backend": "ollama", "degraded": False}}}}
    assert S._state(2, row) != "INFRA"


def test_a_round_with_no_embeddings_reading_is_still_graded():
    """Older rounds and any boot that never logged the line must keep their verdict: an unmeasured
    confound is not evidence of one."""
    row = {"run": {"transcript": ["a", "b", "c", "d"], "mechanism_report": {}}}
    assert S._state(2, row) != "INFRA"
