"""The reranker's ABSOLUTE per-pair score (`rr_abs`) — the only non-relative relevance signal in the read path.

Why this exists at all, and why there is NO relevance floor built on top of it (V2-114 F4.5, measured
2026-08-18): the read path had no absolute notion of relevance. `rel` is the RRF score divided by the fusion's
own maximum, so **the best of a bad lot always scores ~1 by construction**; BM25 is not comparable across
queries. The cross-encoder was already computing exactly the missing quantity — a score for THIS (query, text)
pair, independent of what else came back — and `rerank_local.order()` threw it away to return a permutation.

Exposing it was free. Acting on it was measured and REJECTED, and the numbers are here so nobody re-derives
them: over 269 corpus queries against a 247-pill DB, the score of the CORRECT pill (n=88) and the score of the
BEST candidate on a query whose answer is NOT stored (n=144) overlap almost completely —

    correct pill          p05 -2.820  p50 -1.203  p90 +0.041
    best candidate, no answer stored   p05 -2.681  p50 -1.774  p90 -0.680

0.57 apart at the median. A floor at -2.5 keeps 90.9% of real recall and refuses 13.2% of the unanswerable; at
-3.0 it keeps 97.7% and refuses 1.4%. There is no setting that is worth the recall it costs. The reason is not a
weak model: with 247 pills about the same person, a question whose exact answer is missing still retrieves
genuinely on-topic pills, and a cross-encoder scores topical relevance CORRECTLY — it answers "is this text
about this question", not "does this text contain the answer". Those are different questions and only the second
one licenses a refusal. That job stays with the ANSWERER, which reads the pills and already refuses.

Hand-picked examples said the opposite (a clean -0.70 vs -3.68 separation) and were flattering. That gap between
three chosen cases and 232 measured ones is the reason this file records distributions and not anecdotes.
"""
from __future__ import annotations


from memory import rerank as _rr


def _fake_rank(scores: dict[str, float]):
    """A stand-in cross-encoder: deterministic scores by text, so the test asserts PLUMBING, not model output."""
    def _rank(query, texts, model=None):
        pairs = [(i, scores.get(t, -9.0)) for i, t in enumerate(texts)]
        pairs.sort(key=lambda p: p[1], reverse=True)
        return pairs
    return _rank


def test_rank_keeps_scores_and_order_stays_a_pure_wrapper(monkeypatch):
    """`order()` must be exactly `rank()` minus the scores — two orderings that can disagree is a silent bug."""
    from memory import rerank_local

    monkeypatch.setattr(rerank_local, "_get", lambda m: object())

    class _Enc:
        @staticmethod
        def rerank(q, texts):
            return [-3.0, -0.5, -2.0]

    monkeypatch.setattr(rerank_local, "_get", lambda m: _Enc)
    ranked = rerank_local.rank("q", ["a", "b", "c"])
    assert ranked == [(1, -0.5), (2, -2.0), (0, -3.0)]
    assert rerank_local.order("q", ["a", "b", "c"]) == [1, 2, 0]


def test_scores_available_tracks_the_active_provider(monkeypatch):
    monkeypatch.setattr(_rr, "provider", lambda: "local")
    assert _rr.scores_available() is True
    monkeypatch.setattr(_rr, "provider", lambda: "off")
    assert _rr.scores_available() is False
