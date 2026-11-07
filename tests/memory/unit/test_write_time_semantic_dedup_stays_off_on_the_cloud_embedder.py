"""V2-858 T551 — the write-time semantic dedup stays OFF on the cloud embedder, on purpose.

Measured on the live stock (2026-11-07, text-embedding-3-small): the nearest pairs are DIFFERENT facts — two requests
of one day at L2 0.30, two renewal dates of one insurance at 0.35 — while a true paraphrase sits at 0.56. Any cut
that merges the paraphrase merges the conflicts first. This pins the decision: turning it on needs a new study, not
an edit to the set.
"""
from memory import embeddings as mememb
from memory import writer as memwriter
from memory.writer import policy


def test_only_the_studied_backend_dedups_on_write():
    assert policy._SEMANTIC_DEDUP_CALIBRATED_BACKENDS == {"ollama"}


def test_the_cloud_backend_writes_both_rows(monkeypatch):
    monkeypatch.setattr(mememb, "active_backend", lambda: "cloud")
    monkeypatch.delenv("MEM_SEMANTIC_DEDUP", raising=False)
    assert memwriter._semantic_dedup_on() is False
