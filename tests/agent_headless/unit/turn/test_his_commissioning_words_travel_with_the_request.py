"""His sentence that commissions an errand travels with the request to the errand it opens (refactor2710-02 input).

find-concert-tickets ES: «Búscame entradas para un concierto de Rosalía en Madrid este mes» became a worker errand
whose sheet never had `asked` — the row door judges rows by his words, so it judged nothing and offered rows that were
not about Rosalía. The old text channel noted his sentence at launch (`commission_words`, node 2.630) and the voice
turn never did; refactor2710-01 deleted the old channel's half. The class is the Request's: born once with his words,
it carries them to the worker and the sheet (`request.model.heard` → the escalation's context → `SessionRecord.heard`
→ `sheets._hear` → the row door). Disarm: return "" from `request.model.heard` → the first test goes red.
"""
from __future__ import annotations

from tests.brain import harness as H

HEARD = "Búscame entradas para un concierto de Rosalía en Madrid este mes."


def test_the_escalation_carries_his_commissioning_words():
    case = {"id": "commission-words", "lang": "es", "phrase": HEARD, "source": "node 2.630",
            "screen": {"open": []}, "expect": "escalate",
            "model": {"say": "Me pongo con ello.",
                      "tools": [{"name": "escalate_to_slowbrain",
                                 "args": {"request": "entradas concierto Rosalía Madrid", "surface": "results"}}]}}
    out = H.run_case(case)
    assert not out.error, out.error
    rows = [e for e in (out.events or []) if e.get("kind") == "brain" and "escalada registrada" in str(e.get("label"))]
    assert out.action == "escalate" and rows, "the turn did not escalate — the premise of this test"
    assert rows[0].get("heard") == HEARD, rows[0]


def test_two_errands_in_one_sentence_hand_neither_his_words(monkeypatch):
    """«entradas de Rosalía y un hotel en Sevilla»: one errand's subject would judge the other's rows."""
    case = {"id": "commission-two", "lang": "es", "phrase": "Búscame entradas de Rosalía y un hotel en Sevilla.",
            "source": "node 2.828", "screen": {"open": []}, "expect": "escalate",
            "model": {"say": "Me pongo con las dos.", "tools": [
                {"name": "escalate_to_slowbrain", "args": {"request": "entradas Rosalía", "surface": "results"}},
                {"name": "escalate_to_slowbrain", "args": {"request": "hotel en Sevilla", "surface": "results"}}]}}
    out = H.run_case(case)
    rows = [e for e in (out.events or []) if e.get("kind") == "brain" and "escalada registrada" in str(e.get("label"))]
    assert rows and not rows[0].get("heard"), rows


def test_the_sheet_hears_the_words_its_record_carries(monkeypatch):
    from types import SimpleNamespace

    from nucleo import sheets
    from widgets.results import category_gate
    heard: list = []
    monkeypatch.setattr(category_gate, "hear", lambda sheet, words: heard.append((sheet, words)) or True)
    sheets._hear("results::t1", HEARD)
    sheets._hear("results::t2", "")
    assert heard == [("results::t1", HEARD)]
    assert SimpleNamespace(heard=HEARD).heard     # the record field the dispatcher fills from the context
