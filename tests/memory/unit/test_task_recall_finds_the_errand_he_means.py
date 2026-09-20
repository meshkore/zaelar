"""V2-728 F5 — «de la tarea de buscar piso que te dije antes».

Nothing in this engine could answer that. Disambiguation reached what is on screen (`widgets/instances.py`)
or the six-entry `recent_widgets` MRU; a commission that closed last week is neither, and its sheet may have
been pruned by the eight-sheet cap. The shape is the operator's own rule (INI-027 §7): an INDEX narrows, a
MODEL chooses — and with several equally good candidates, nobody chooses and we ask.
"""
import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo.flash import task_recall as tr
from widgets import store


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


@pytest.fixture
def own_sheets(tmp_path, monkeypatch):
    """A widget data dir of our OWN.

    `widgets/store.DATA_DIR` is a module constant computed at import time from `workspace.root()`, so setting
    `ZAELAR_WORKSPACE` after the fact reaches nothing and neither does patching `workspace.root` — the two
    obvious moves both LOOK like isolation and leave the test writing into the operator's real
    `widgets/_data/`. Measured while writing this file: a sheet called `results--t1` appeared in his tree.
    Patching the constant is the one that bites, and the assertion below is the guard for the guard.
    """
    d = tmp_path / "wdata"
    d.mkdir()
    monkeypatch.setattr(store, "DATA_DIR", str(d))
    assert "widgets/_data" not in store.DATA_DIR, "this fixture is not isolating anything"
    return d


@pytest.fixture(autouse=True)
def no_jev(monkeypatch):
    """Jev OFF by default: every case that does not name it must be decided WITHOUT a model."""
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: False)
    return jev


def _done(tid, title, goal, outcome="", created=1000):
    ts.task_put({"id": tid, "title": title, "goal": goal, "state": "done", "outcome": outcome,
                 "created_at": created, "finished_at": created + 60})


# ── the index half: no model, ≤5 ────────────────────────────────────────────────────────────────────────
def test_the_candidate_search_never_calls_a_model(fresh_db, monkeypatch):
    """The rule is not «cheap», it is «no model». A classifier in the narrowing step is what INI-027 §7 bans."""
    import nucleo.jev as jev
    calls = []
    monkeypatch.setattr(jev, "select_many", lambda *a, **k: calls.append(1) or [])
    monkeypatch.setattr(jev, "choose_many_sync", lambda *a, **k: calls.append(1) or {})
    _done("t1", "piso en Gràcia", "búscame piso de alquiler en Gracia")
    assert [c["id"] for c in tr.candidates("lo del piso")] == ["t1"]
    assert calls == []


def test_it_hands_over_at_most_five(fresh_db):
    for n in range(9):
        _done(f"t{n}", f"piso número {n}", "búscame piso", created=1000 + n)
    assert len(tr.candidates("piso")) == 5


# ── one candidate: taken without paying for a verdict ───────────────────────────────────────────────────
def test_one_candidate_is_taken_without_asking_jev(fresh_db, monkeypatch):
    """Paying 800 ms to confirm what nothing contradicts is the call V2-726 exists to stop making."""
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: True)
    called = []
    monkeypatch.setattr(jev, "select_many", lambda *a, **k: called.append(1) or [])
    _done("t1", "piso en Gràcia", "búscame piso de alquiler en Gracia")
    r = tr.resolve("lo del piso que te dije")
    assert r["ok"] and r["task"]["id"] == "t1" and r["how"] == "único"
    assert called == [], "Jev was asked to choose between one thing"


def test_nothing_that_matches_is_said_plainly(fresh_db):
    _done("t1", "mesa para 4", "resérvame mesa")
    r = tr.resolve("lo del piso")
    assert r["ok"] is False and r["ask"] == []


# ── several candidates: Jev chooses, or we ask ──────────────────────────────────────────────────────────
def test_jev_picks_the_one_he_means(fresh_db, monkeypatch):
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: True)
    seen = {}

    def _pick(cands, criteria, *, key=None, label=None, **kw):
        seen["criteria"] = criteria
        seen["labels"] = [label(c) for c in cands]
        chosen = next(c for c in cands if c["id"] == "t2")
        return [{"key": key(chosen), "candidate": chosen, "fit": "strong", "confidence": 0.9}]

    monkeypatch.setattr(jev, "select_many", _pick)
    _done("t1", "piso en Gràcia", "búscame piso de alquiler en Gracia", created=1000)
    _done("t2", "piso en Sants", "búscame piso de alquiler en Sants", "3 opciones", created=2000)
    r = tr.resolve("el piso de Sants")
    assert r["ok"] and r["task"]["id"] == "t2" and r["how"] == "jev"
    # what the chooser was given: HIS sentence as the criteria, and each candidate with its outcome
    assert "el piso de Sants" in seen["criteria"]
    assert any("3 opciones" in x for x in seen["labels"])


def test_two_equally_good_candidates_are_a_QUESTION_not_a_pick(fresh_db, monkeypatch):
    """The rule `widgets/directory.py:176` already keeps for contacts, and it matters more here: opening the
    wrong report looks exactly like opening the right one, and he would read it before noticing."""
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "select_many", lambda cands, criteria, *, key=None, label=None, **kw: [
        {"key": key(c), "candidate": c, "fit": "strong", "confidence": 0.9} for c in cands])
    _done("t1", "piso en Gràcia", "búscame piso", created=1000)
    _done("t2", "piso en Sants", "búscame piso", created=2000)
    r = tr.resolve("lo del piso")
    assert r["ok"] is False
    assert {x["id"] for x in r["ask"]} == {"t1", "t2"}


def test_a_jev_that_narrows_makes_the_question_SHORTER(fresh_db, monkeypatch):
    """A question listing five reports is not a question. If the chooser ruled some out, ask about the rest."""
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "select_many", lambda cands, criteria, *, key=None, label=None, **kw: [
        {"key": key(c), "candidate": c, "fit": "strong", "confidence": 0.9}
        for c in cands if c["id"] in ("t1", "t2")])
    for n in range(1, 5):
        _done(f"t{n}", f"piso {n}", "búscame piso", created=1000 + n)
    r = tr.resolve("lo del piso")
    assert r["ok"] is False and {x["id"] for x in r["ask"]} == {"t1", "t2"}


def test_a_jev_that_is_down_asks_instead_of_guessing(fresh_db, monkeypatch):
    """The chooser is advisory everywhere in `nucleo/jev.py`, and the safe fallback here is the question."""
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "select_many", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    _done("t1", "piso en Gràcia", "búscame piso", created=1000)
    _done("t2", "piso en Sants", "búscame piso", created=2000)
    r = tr.resolve("lo del piso")
    assert r["ok"] is False and len(r["ask"]) == 2


# ── and then it is PUT BACK on screen ───────────────────────────────────────────────────────────────────
def test_the_report_comes_back_even_though_its_sheet_was_pruned(fresh_db, own_sheets):
    """The end-to-end reason all of this exists. The sheet is gone; the task kept the payload."""
    _done("t1", "piso en Gràcia", "búscame piso de alquiler en Gracia", "5 pisos")
    ts.artifact_put("t1", "result", {"title": "piso en Gràcia",
                                     "items": [{"title": f"piso {i}"} for i in range(5)]})
    ts.artifact_put("t1", "criteria", {"goal": "piso de 2 habitaciones en Gràcia",
                                       "hard": ["2 habitaciones", "ascensor"]})
    out = tr.recall_and_reopen("enséñame lo del piso que te dije")
    assert out["ok"], out
    assert out["instance"] == "results::t1"
    assert out["rebuilt"] is True
    from widgets.results import lifecycle as _lc
    back = _lc.view_data("t1")
    assert len(back["items"]) == 5
    assert back["criteria"]["goal"] == "piso de 2 habitaciones en Gràcia"
    assert back["criteria"]["hard"] == ["2 habitaciones", "ascensor"]


def test_reopening_twice_does_not_rebuild_over_what_is_already_there(fresh_db, own_sheets):
    """Overwriting a sheet that still exists would discard anything added since the errand closed — the
    «error de borrar búsquedas» this whole lineage exists to remove."""
    _done("t1", "piso en Gràcia", "búscame piso")
    ts.artifact_put("t1", "result", {"title": "piso en Gràcia", "items": [{"title": "uno"}]})
    assert tr.recall_and_reopen("lo del piso")["rebuilt"] is True
    assert tr.recall_and_reopen("lo del piso")["rebuilt"] is False


def test_a_task_that_kept_nothing_says_so(fresh_db, own_sheets):
    """An empty sheet would look like a report that came back with nothing — a different answer entirely."""
    _done("t1", "piso en Gràcia", "búscame piso")
    out = tr.recall_and_reopen("lo del piso")
    assert out["ok"] is False


def test_the_ambiguity_reaches_the_caller_as_names_it_can_read_aloud(fresh_db, monkeypatch):
    import nucleo.jev as jev
    monkeypatch.setattr(jev, "enabled", lambda: True)
    monkeypatch.setattr(jev, "select_many", lambda cands, criteria, *, key=None, label=None, **kw: [])
    _done("t1", "piso en Gràcia", "búscame piso", created=1000)
    _done("t2", "piso en Sants", "búscame piso", created=2000)
    out = tr.recall_and_reopen("lo del piso")
    assert out["ok"] is False
    assert {x["title"] for x in out["ask"]} == {"piso en Gràcia", "piso en Sants"}
