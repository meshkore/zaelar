"""V2-707 F2 · The HARNESS: the worker declares how success is measured, and the engine checks it.

## What he asked (2026-09-16)

> «Asegúrate también de que encajas el arnés… que debe manejar, me imagino, el Brainworker, también tiene
> que estar ahí. Es decir, tiene que saber identificar la tarea que ha propuesto el usuario y determinar
> cuál es la manera de medir el éxito. Y así, después de todo el proceso, podemos ver si hemos llegado a ese
> punto. Si no hemos llegado, entiendo que es capaz de iterar hasta que lo consiga. Y si hiciéramos ese
> bucle, probablemente muchas tareas no quedarían huérfanas o a medias.»

The engine had three fragments and no whole: `harness.py` verifies one class for five minutes in RAM,
`errands/verify.py` verifies one hand-written condition, and the Brain Worker verified NOTHING — `_finish`
closed on `rec.ok`, which the worker sets itself, while the prompt asked it in prose to «VERIFICA… ITERA».
A rail on judgement, which `principles.md` says to replace with a mechanism.

So: **the model writes the condition** (it is the one that understood the errand) **and the engine checks
it** against the product's own truth. That asymmetry is the whole design.

Three answers and only one retries. `None` — nothing declared, or unreadable — is never failure: the V2-660
rule kept verbatim, because a wrong «you did not deliver» over a delivered errand is worse than silence.
"""
from __future__ import annotations

import pytest

from nucleo import verify


@pytest.fixture
def agenda(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.agenda import data as ag
    db = ag.load_db()
    db["meetings"] = [
        {"id": "m1", "title": "Meeting with Cryptonite", "date": "2035-01-02", "startTime": "17:00"},
        {"id": "m2", "title": "Dentist", "date": "2035-01-01", "startTime": "17:00"},
    ]
    store.save(ag.WIDGET_ID, db)
    return ag


GONE = {"all": [{"widget": "agenda", "collection": "meetings",
                 "where": {"title~": "Cryptonite"}, "expect": "absent"}]}
THERE = {"all": [{"widget": "agenda", "collection": "meetings",
                  "where": {"title~": "Cryptonite"}, "expect": "present"}]}


# ── the grammar: closed in OPERATORS, open in CONTENT ──────────────────────────────────────────────────

def test_the_condition_reads_the_products_own_truth(agenda):
    assert verify.check(THERE) is True
    assert verify.check(GONE) is False


def test_and_it_changes_when_the_product_does(agenda):
    from widgets import store
    db = agenda.load_db()
    db["meetings"] = [m for m in db["meetings"] if "Crypto" not in m["title"]]
    store.save(agenda.WIDGET_ID, db)
    assert verify.check(GONE) is True and verify.check(THERE) is False


@pytest.mark.parametrize("clause,expected", [
    ({"widget": "agenda", "collection": "meetings", "where": {"date>=": "2035-01-02"}}, True),
    ({"widget": "agenda", "collection": "meetings", "where": {"date>=": "2099-01-01"}}, False),
    ({"widget": "agenda", "collection": "meetings", "count": 2}, True),
    ({"widget": "agenda", "collection": "meetings", "count": 3}, False),
    ({"widget": "agenda", "collection": "meetings", "count": {"min": 1}}, True),
    ({"widget": "agenda", "collection": "meetings", "count": {"max": 1}}, False),
])
def test_what_a_clause_may_ask(agenda, clause, expected):
    assert verify.check_clause(clause) is expected


def test_any_needs_only_one_and_all_needs_every_one(agenda):
    assert verify.check({"any": [GONE["all"][0], THERE["all"][0]]}) is True
    assert verify.check({"all": [GONE["all"][0], THERE["all"][0]]}) is False


def test_the_condition_speaks_the_SAME_expression_as_the_data_door(agenda):
    """Not a coincidence and worth pinning: both answer «which rows match», so they share the selector and
    cannot drift into disagreeing about the same calendar — which is the defect F0 had just fixed."""
    from widgets import rows
    where = {"title~": "crypto"}
    assert bool(rows.select("agenda", "meetings", where)) is verify.check_clause(
        {"widget": "agenda", "collection": "meetings", "where": where})


# ── None is «cannot be read», and it is NEVER a failure ────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    {}, None, [], "done",
    {"all": []},
    {"all": [{"widget": "agenda", "collection": "facturas", "where": {}}]},   # no such collection
    {"all": [{"widget": "clock", "where": {}}]},                              # widget holds no rows
    {"all": [{"widget": "agenda", "collection": "meetings", "expect": "sort_of"}]},   # unknown operator
    {"all": [{"collection": "meetings"}]},                                    # no widget named
])
def test_an_unreadable_condition_answers_None_not_False(agenda, bad):
    assert verify.check(bad) is None, bad


def test_a_widget_with_two_collections_and_no_name_is_not_guessed(agenda):
    """The agenda holds meetings, tasks and projects. Picking one would be the class of error this file
    exists to stop, so it reads as unverifiable instead."""
    assert verify.check_clause({"widget": "agenda", "where": {}}) is None


def test_a_single_collection_widget_needs_no_name(agenda):
    assert verify.check_clause({"widget": "contactos", "where": {}}) in (True, False)


def test_the_checker_never_raises(agenda, monkeypatch):
    from widgets import rows
    monkeypatch.setattr(rows, "select", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))
    assert verify.check(GONE) is None


# ── what is MISSING is said, so the retry starts from the gap ──────────────────────────────────────────

def test_the_gap_is_named(agenda):
    falta = verify.missing(GONE)
    assert falta and "agenda.meetings" in falta[0] and "Cryptonite" in falta[0]


def test_a_met_condition_names_no_gap(agenda):
    assert verify.missing(THERE) == []


# ── the loop: measure before delivering, iterate once, then tell the truth ─────────────────────────────

def _finished(rec, monkeypatch, escalations):
    """Drive the REAL harness over a record, with the escalation stubbed so nothing is launched."""
    from nucleo.flash import escalate as esc
    from nucleo.workers import goal
    monkeypatch.setattr(esc, "escalate_to_slowbrain",
                        lambda req, context=None: escalations.append((req, context or {})) or 1)
    goal.check_and_relay(rec, relay_cap=2)
    return rec


def _rec(**kw):
    from nucleo.workers.session import SessionRecord
    r = SessionRecord(task_id="t1", goal="cancela la cita con Cryptonite y avísale")
    r.ok = True
    r.result_summary = "Listo, cancelada y avisado."
    for k, v in kw.items():
        setattr(r, k, v)
    return r


def test_a_worker_that_claims_success_over_an_UNMET_goal_is_relaunched(agenda, monkeypatch):
    """The measured shape of 2026-09-16, one layer up: the meeting is still in the agenda and the sentence
    says it is cancelled. Nothing in the engine compared the two."""
    escalations: list = []
    rec = _finished(_rec(done_when=GONE), monkeypatch, escalations)
    assert escalations, "an unmet goal has to be retried, not delivered"
    req, ctx = escalations[0]
    assert "[ARNÉS]" in req and "Cryptonite" in req, req
    assert ctx["done_when"] == GONE, "the relay must carry the bar, or the retry is the last unchecked one"
    assert rec.handoff and rec.ok is False and rec.result_summary == ""


def test_a_MET_goal_is_delivered_untouched(agenda, monkeypatch):
    escalations: list = []
    rec = _finished(_rec(done_when=THERE), monkeypatch, escalations)
    assert escalations == []
    assert rec.ok is True and rec.result_summary == "Listo, cancelada y avisado."


def test_a_goal_NOBODY_declared_changes_nothing(agenda, monkeypatch):
    """Most errands (a search, a report) end in no readable widget state. They must be untouched."""
    escalations: list = []
    rec = _finished(_rec(), monkeypatch, escalations)
    assert escalations == [] and rec.ok is True


def test_an_UNREADABLE_goal_neither_retries_nor_accuses(agenda, monkeypatch):
    escalations: list = []
    rec = _finished(_rec(done_when={"all": [{"widget": "agenda", "collection": "facturas"}]}),
                    monkeypatch, escalations)
    assert escalations == [] and rec.ok is True, "None is «cannot be read», never «failed»"


def test_the_second_failure_tells_the_operator_the_TRUTH(agenda, monkeypatch):
    """«Iterar hasta que lo consiga» cannot mean forever. When the budget is gone the errand is not
    delivered as done — it says what is missing, which is the V2-238 rule at this gate."""
    escalations: list = []
    rec = _finished(_rec(done_when=GONE, goal_retried=True), monkeypatch, escalations)
    assert escalations == [], "no second automatic retry"
    assert rec.ok is False
    assert "Queda:" in rec.result_summary and "Cryptonite" in rec.result_summary
    assert "Listo, cancelada" in rec.result_summary, "what it DID achieve is not thrown away"


def test_a_cancelled_task_is_not_judged(agenda, monkeypatch):
    escalations: list = []
    rec = _finished(_rec(done_when=GONE, status="cancelled"), monkeypatch, escalations)
    assert escalations == [] and "Queda:" not in rec.result_summary


# ── the declaration reaches the record ─────────────────────────────────────────────────────────────────

def test_the_worker_declares_the_bar_and_it_lands_on_its_record():
    from nucleo import dispatch
    from nucleo.workers.session import SessionRecord
    dispatch._SESSIONS["tz"] = SessionRecord(task_id="tz", goal="x")
    try:
        from nucleo.workers.goal import session_goal
        session_goal("tz", GONE)
        assert dispatch._SESSIONS["tz"].done_when == GONE
        session_goal("tz", {})                   # an empty re-declaration must not retire the bar
        assert dispatch._SESSIONS["tz"].done_when == GONE
    finally:
        dispatch._SESSIONS.pop("tz", None)


def test_the_bridge_refuses_a_goal_that_is_not_JSON_and_says_the_shape(capsys):
    from nucleo import agent_report
    assert agent_report.main(["goal", "{nope"]) == 2
    out = capsys.readouterr().out
    assert "no es JSON válido" in out and "expect" in out and "hbwidget read" in out


def test_the_worker_is_TOLD_it_can_declare_a_bar():
    """A capability nobody declares is one the model narrates instead of using (V2-540)."""
    from nucleo import dispatch_prompts
    block = dispatch_prompts._METHOD_BLOCK
    assert "agent_report goal" in block and "done_when" not in block.split("goal")[0][-200:]
    assert "no declares nada" in block, (
        "and it has to be told when NOT to declare one — a condition invented for a search is a retry loop")


def test_the_harness_is_WIRED_INTO_the_ending_and_runs_BEFORE_delivery():
    """Caught by its own disarm: every case above drives `goal.check_and_relay` directly, so unhooking it
    from `_finish` left the whole file green while the mechanism was dead. A measure taken AFTER the
    operator has already been told is not a measure, so the order is pinned too."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[4] / "nucleo" / "workers" / "session.py"
           ).read_text(encoding="utf-8")
    body = src[src.index("    async def _finish(self)"):]
    body = body[:body.index("\n    async def ") if "\n    async def " in body[10:] else len(body)]
    assert "_harness(rec" in body, "`_finish` no longer measures the declared end state"
    assert body.index("_harness(rec") < body.index("await _deliver(rec)"), (
        "the harness has to run BEFORE delivery — measuring after telling him it is done is not measuring")
