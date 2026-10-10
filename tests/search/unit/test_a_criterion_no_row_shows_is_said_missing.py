"""A criterion NO row can show is said missing, never implied met (V2-782 T3.2).

best-plumber-same-day ES (2026-10-10): seventeen names from a network agent, no rating, no slot, and the turn
offered them as «the best-rated who can come today». The rows carried nothing but a name and a link — that is
a fact about the rows, and presenting them as meeting the criterion is the lie the sheet's digest now blocks.
"""
from __future__ import annotations

import json
from pathlib import Path

from search import candidacy

SHEETS = Path(__file__).resolve().parents[1] / "fixtures" / "sheets"
CRIT = {"hard": ["rating / reviews", "availability (when)"]}


def test_names_only_rows_cannot_show_any_criterion():
    items = json.loads(next(SHEETS.glob("best-plumber-same-day__es*.json")).read_text(encoding="utf-8"))["items"]
    names_only = [i for i in items if not i.get("price") and all(f.get("label") == "Origen" for f in i.get("facts") or [])]
    assert len(names_only) >= 5, "the network agent's rows: a name, a link, nothing else"
    assert candidacy.unshown_criteria(names_only, CRIT) == CRIT["hard"]
    assert candidacy.unshown_criteria(items, CRIT) == [], "one later row with a phone is a datum — structural, not semantic"


def test_one_row_with_a_datum_is_enough_to_stop_saying_it():
    items = json.loads(next(SHEETS.glob("best-plumber-same-day__en*.json")).read_text(encoding="utf-8"))["items"]
    assert candidacy.unshown_criteria(items, CRIT) == []


def test_no_criteria_or_no_rows_says_nothing():
    assert candidacy.unshown_criteria([], CRIT) == []
    assert candidacy.unshown_criteria([{"title": "x"}], {}) == []
    assert candidacy.unshown_criteria([{"title": "x"}], {"hard": []}) == []


def test_the_prompt_digest_tells_the_turn(monkeypatch, tmp_path):
    from widgets.results import digest
    data = {"title": "Fontaneros", "items": [{"title": "Fontanería A", "url": "https://a"}, {"title": "Fontanería B"}],
            "criteria": {"hard": ["rating / reviews"]}}
    text = digest.one(data)
    assert "NINGUNA fila trae dato" in text and "rating / reviews" in text


def test_find_marks_the_asked_fields_no_candidate_shows(monkeypatch):
    import search
    from search import web
    monkeypatch.setattr(web, "search", lambda q, k=5, mode="answer": {
        "query": q, "answer": "", "source": "zai",
        "results": [{"title": "Fontaneros Madrid - HomeServe", "snippet": "acudirá de inmediato", "url": "https://homeserve.es"},
                    {"title": "Fontaneros Urgentes en Madrid", "snippet": "24/7", "url": "https://rubio.es"}]})
    res = search.find("el fontanero mejor valorado que pueda venir hoy", route="local_service")
    assert res.route == "local_service" and len(res.candidates) == 2
    assert res.criteria["hard"] == ["rating / reviews", "availability (when)"]
    assert res.unshown == ["rating / reviews", "availability (when)"], "two names and two links show neither"
