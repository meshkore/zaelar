"""V2-858 T549 — one concept hub per meaning, whatever language each pill was labelled in.

Measured origin (live store, 2026-11-06): 71 concept hubs in two languages, the car alone spread over ten
(car/cars/coche/coches/vehicle/vehicles/transport/transporte/mobility/motor). A category question matched one hub
and `graph_expand` brought only its pills, so «¿cómo va lo del coche?» reached a tenth of what he had said about it.

Neither a word table nor the embedding of a bare word folds them (measured: salud~health 0.53 < car~home 0.55),
so the GROUPING is a model's call in sleep and everything else is deterministic, tested here with the model stubbed:
  · the fold moves every edge to one canonical hub (the most-used), invalidates the rest pointing at it, and
    keeps the folded names as aliases (FTS in both languages, and the writer keeps resolving them);
  · the plan is fail-closed: invented labels, groups of one and overlapping groups are dropped;
  · the phase costs no model call when the hub set did not change, and a model failure folds nothing;
  · the distiller is shown the hubs that exist, so new pills reuse them instead of opening a new language.
"""
import time

import pytest

from memory import api as memapi
from memory import concepts as memconcepts
from memory import consolidator as memcons
from memory import db as memdb
from memory import embeddings as mememb
from memory import writer as memwriter


@pytest.fixture(autouse=True)
def _hash_backend(monkeypatch):
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    monkeypatch.setenv("MEMORY_RERANK", "off")
    mememb.reset()
    yield
    mememb.reset()


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


CAR_PILLS = [
    ("Drives a 2019 Toyota Corolla.", ["car"]),
    ("Paid 410 euros for the Corolla's insurance.", ["car", "finances"]),
    ("Tiene que pasar la ITV del Corolla en marzo.", ["coche"]),
    ("Le cambiaron las ruedas al Corolla.", ["coche"]),
    ("Wants an electric vehicle next year.", ["vehicle"]),
]


def _seed():
    return [memwriter.insert_memory(t, level="long", kind="fact", concepts=c) for t, c in CAR_PILLS]


def _hub(name):
    return memdb.get_db().query_one("SELECT id, valid, superseded_by, meta FROM memories WHERE kind='concept' "
                                    "AND text=?", (name,))


def _pills_of(hub_id):
    return {r["from_id"] for r in memdb.get_db().query("SELECT from_id FROM edges WHERE to_id=?", (hub_id,))}


def _group(groups):
    calls = []

    def fn(names):
        calls.append(list(names))
        return groups
    fn.calls = calls
    return fn


def test_the_fold_puts_every_car_pill_under_one_hub(fresh_db):
    ids = _seed()
    rep = memapi.fold_concepts(_group([["car", "coche", "vehicle"]]))
    assert rep["folded"] == 2
    canon = _hub("car")                                    # three edges in: the most-used hub is the canonical
    assert canon["valid"] == 1 and _pills_of(canon["id"]) == set(ids)
    for alias in ("coche", "vehicle"):
        h = _hub(alias)
        assert h["valid"] == 0 and h["superseded_by"] == canon["id"]   # history kept, pointed at its canonical
        assert _pills_of(h["id"]) == set()
    assert _pills_of(_hub("finances")["id"]) == {ids[1]}, "an unrelated hub must not move"


def test_a_folded_name_keeps_resolving_to_its_canonical(fresh_db):
    _seed()
    memapi.fold_concepts(_group([["car", "coche", "vehicle"]]))
    later = memwriter.insert_memory("Vendió el Corolla en noviembre.", level="long", kind="event",
                                    concepts=["coche"])
    assert later in _pills_of(_hub("car")["id"])
    n = memdb.get_db().query_one("SELECT COUNT(*) c FROM memories WHERE kind='concept' AND valid=1 "
                                 "AND text IN ('coche','vehicle')")["c"]
    assert n == 0, "the next pill that said «coche» reopened the folded hub"


def test_a_category_question_in_either_language_reaches_the_whole_cluster(fresh_db):
    ids = _seed()

    def reached(q):
        return set(memapi.query(q, lexical_only=True, reinforce_used=False, limit=12)["ids"]) & set(ids)
    before = reached("vehicle")
    memapi.fold_concepts(_group([["car", "coche", "vehicle"]]))
    assert before < set(ids), "the scenario must start split, or it proves nothing"
    for q in ("coche", "vehicle", "car"):
        assert reached(q) == set(ids), f"«{q}» reached {sorted(reached(q))} of {sorted(ids)}"


def test_the_plan_is_fail_closed():
    hs = [{"id": 1, "name": "car", "edges": 9}, {"id": 2, "name": "coche", "edges": 4},
          {"id": 3, "name": "travel", "edges": 5}, {"id": 4, "name": "viajes", "edges": 7}]
    assert memconcepts.plan_fold(hs, [["car", "coche", "automóvil"]]) == {"coche": "car"}   # invented label dropped
    assert memconcepts.plan_fold(hs, [["car"]]) == {}                                         # a group of one
    assert memconcepts.plan_fold(hs, [["car", "coche"], ["coche", "travel"]]) == {"coche": "car"}  # claimed twice
    assert memconcepts.plan_fold(hs, [["travel", "viajes"]]) == {"travel": "viajes"}         # most-used wins
    assert memconcepts.plan_fold(hs, "garbage") == {}


def test_the_phase_calls_no_model_when_nothing_changed_and_folds_nothing_on_failure(fresh_db):
    _seed()
    assert memapi.fold_concepts(lambda names: None)["skipped"] == "no_model"
    assert _hub("coche")["valid"] == 1
    fn = _group([["car", "coche", "vehicle"]])
    memapi.fold_concepts(fn)
    memapi.fold_concepts(fn)
    assert len(fn.calls) == 1, "the second sleep paid a model call for an unchanged hub set"


def test_light_sleep_does_not_re_prune_a_folded_hub(fresh_db):
    _seed()
    memapi.fold_concepts(_group([["car", "coche", "vehicle"]]))
    memcons.prune_invalid(now=int(time.time()) + 10 * 86400)
    assert memdb.get_db().query_one("PRAGMA integrity_check")[0] == "ok"
    memdb.get_db().execute("INSERT INTO fts_memories(fts_memories) VALUES ('integrity-check')")  # raises if corrupt


def test_the_distiller_is_shown_the_hubs_that_exist(fresh_db):
    from nucleo.memory_agent.processor import distill_prompt
    assert "CONCEPTOS QUE YA EXISTEN" not in distill_prompt.render("hola", {})     # empty memory → zero tokens
    _seed()
    memapi.fold_concepts(_group([["car", "coche", "vehicle"]]))
    out = distill_prompt.render("mi coche hace un ruido raro", {})
    line = next(l for l in out.splitlines() if l.startswith("CONCEPTOS QUE YA EXISTEN"))
    assert "car" in line and "coche" not in line.split(":", 1)[1].replace("«coche»", "")


def test_the_fold_is_wired_as_a_deep_sleep_phase(fresh_db, monkeypatch):
    """The fold only runs if the brain registered it: importing the memory agent registers `concepts` in REM,
    with the model hook the phase injects (stubbed here: no network)."""
    from memory import rem
    from nucleo.memory_agent import concept_fold
    from nucleo.memory_agent.processor import llm_tasks
    import nucleo.memory_agent  # noqa: F401 — the import that registers the phase
    assert rem._PHASES.get("concepts") is concept_fold.rem_pass
    _seed()
    monkeypatch.setattr(llm_tasks, "group_concepts", lambda names: [["car", "coche", "vehicle"]])
    assert concept_fold.rem_pass()["folded"] == 2
    assert _hub("coche")["valid"] == 0
