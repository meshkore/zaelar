"""A past errand he names by a word only its title has is THAT errand — no chooser, no question (2026-10-14).

`flat-hunt-recall-the-report__es` (1/5): two flat hunts on file, Gràcia and Sant Antoni, and he said «el de
Gràcia». The chooser scored the right one `strong` at 0.19 — under its 0.5 floor — so nothing was picked and the
turn asked him again for the word he had just said. The index already knew: «gracia» is in one title and not in
the other (`nucleo/turn/task_recall.py`).
"""
import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.turn import task_recall as tr
from nucleo.turn import task_recall as named


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def jev_rejects_everything(monkeypatch):
    """Jev ON and answering «no match» — so a pick can only have come from the index, and a call is counted."""
    import nucleo.jev as jev
    calls = []
    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "select_many_status", lambda *a, **k: calls.append(1) or ([], jev.NO_MATCH))
    return calls


def _two_flat_hunts():
    for tid, title, goal, at in (("g", "Pisos de alquiler en Gràcia", "piso de alquiler en Gràcia hasta 1.200 €/mes", 2000),
                                 ("s", "Pisos de alquiler en Sant Antoni", "piso de alquiler en Sant Antoni", 1000)):
        ts.task_put({"id": tid, "title": title, "goal": goal, "state": "done", "visible": True,
                     "created_at": at, "finished_at": at + 60})


def test_the_district_he_names_picks_its_errand_without_asking_the_chooser(fresh_db, jev_rejects_everything):
    _two_flat_hunts()
    r = tr.resolve("piso en Gràcia que te pedí hace unos días")
    assert r["ok"] and r["task"]["id"] == "g" and r["how"] == "nombrado", r
    assert jev_rejects_everything == [], "the index had the answer; the chooser was paid for nothing"


def test_the_name_matches_without_its_accent(fresh_db, jev_rejects_everything):
    _two_flat_hunts()
    assert tr.resolve("el de gracia")["task"]["id"] == "g"
    assert tr.resolve("el de Sant Antoni")["task"]["id"] == "s"


def test_words_both_errands_share_are_still_a_question(fresh_db, jev_rejects_everything):
    _two_flat_hunts()
    r = tr.resolve("lo del piso de alquiler que te dije")
    assert r["ok"] is False and {x["id"] for x in r["ask"]} == {"g", "s"}


def test_naming_both_is_a_contradiction_and_a_question(fresh_db, jev_rejects_everything):
    _two_flat_hunts()
    r = tr.resolve("no el de Gràcia, el de Sant Antoni")
    assert r["ok"] is False and len(r["ask"]) == 2


def test_a_word_only_the_goal_carries_names_nothing():
    """«…under $3,200/month» is in one GOAL; «the one I told you about last month» must not pick it."""
    rows = [{"id": "w", "title": "Apartments for rent in Williamsburg",
             "goal": "apartment for rent in Williamsburg under $3,200/month"},
            {"id": "a", "title": "Apartments for rent in Astoria", "goal": "apartment for rent in Astoria"}]
    assert named.named(rows, "the apartment I told you about last month") is None
    assert named.named(rows, "the Williamsburg one")["id"] == "w"
