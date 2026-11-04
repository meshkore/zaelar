"""The search bench judges blind: no provider's name reaches the judge, the order is shuffled, and a letter the
judge skipped scores zero (`tests/search/live/bench.py`, V2-782). Its cases are the public catalogue, one per mode."""
from __future__ import annotations

import json
import random

from tests.search.live import bench

_BLOCKS = {
    "perplexity": {"answer": "Abre a las 10:00.", "results": [{"title": "Horarios", "snippet": "10-20 h", "url": "https://museodelprado.es"}]},
    "brave": {"answer": "", "results": [{"title": "Museo", "snippet": "", "url": "https://x.es"}]},
    "tavily": {"answer": "", "results": []},
}


def test_no_provider_name_reaches_the_judge():
    text, letters = bench.blind(_BLOCKS, random.Random(1))
    assert sorted(letters.values()) == sorted(_BLOCKS)
    for name in _BLOCKS:
        assert name not in text.lower(), name
    assert "(nothing)" in text and "Abre a las 10:00." in text


def test_the_order_is_shuffled():
    orders = {tuple(bench.blind(_BLOCKS, random.Random(seed))[1].values()) for seed in range(12)}
    assert len(orders) > 1


def test_the_judges_letters_come_back_as_providers_and_a_skipped_one_scores_zero():
    _, letters = bench.blind(_BLOCKS, random.Random(3))
    first, second = list(letters)[:2]
    got = bench.scores_from('Sure: {"scores": {"%s": 8, "%s": 3}}' % (first, second), letters)
    assert got[letters[first]] == 8 and got[letters[second]] == 3 and got[letters["C"]] == 0


def test_the_summary_ranks_by_score_and_counts_errors():
    rows = [{"scores": {"a": 8, "b": 4}, "lat": {"a": 2.0, "b": 1.0}, "err": {"b": "429"}},
            {"scores": {"a": 6, "b": 6}, "lat": {"a": 3.0, "b": 1.5}, "err": {}}]
    s = bench.summary(rows)
    assert list(s) == ["a", "b"] and s["a"]["score"] == 7.0 and s["b"]["errors"] == 1


def test_every_mode_has_cases_in_both_languages():
    cases = json.loads(bench.CASES.read_text(encoding="utf-8"))
    for mode in ("fact", "leads", "local"):
        assert {c["lang"] for c in cases[mode]} == {"es", "en"}, mode
    assert all(c.get("near") for c in cases["local"]), "a local case names its place"
