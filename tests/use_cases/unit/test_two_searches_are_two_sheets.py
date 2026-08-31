"""TWO searches are TWO sheets—and the harness must be able to COUNT the boxes, not merely look inside one.

Operator rule (2026-08-21): two errands at once are two browsers and two result sheets, each with its
correlation_id; and a finished sheet is NOT reused for the next errand. The reason is that reusing the box
ERASES a search, and an erased search cannot be recovered.

`widget_ops` cannot answer this, and that is not an oversight on its part: it deliberately collapses the
instance (`raw.split("::")[0]`) because the question it answers is “which widget was touched?”. Here the
question is “how many BOXES were there for the same widget?”, and collapsing the instance erases that—it
would say “results touched 9 times” both with one sheet and with three, and that answer is equally credible
in both cases.

TODAY the engine opens only ONE sheet (`dispatch._sheet_open()` emits the bare id and `widgets/results/data.py`
stores it under one key), so the reader returns `shared: true`—which is the exact signature of the defect and
what turns the product rule into a verifiable fact. Once instantiation lands, the same reader returns 2 without
changing a line.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import scenarios as SC, verify as V


def _ev(wid: str, label: str = "show", src: str = "") -> dict:
    """The REAL shape of the event, not an invented one: `observer.emit` does `ev.update(extra)`, so `id` and
    `src` land FLAT in the payload, and the payload arrives as a JSON string from the API."""
    import json
    return {"payload": json.dumps({"cat": "widget", "label": label, "id": wid, "src": src})}


# ── what the engine does TODAY ───────────────────────────────────────────────────────────────────────────
def test_one_box_for_two_errands_is_reported_as_SHARED():
    got = V.sheet_instances([_ev("results", src="worker:t1"), _ev("results", src="worker:t2")])
    assert got["n_sheets"] == 1
    assert got["n_errands"] == 2
    assert got["shared"] is True


def test_reopening_the_same_sheet_is_not_a_second_sheet():
    """What is counted is BOXES, not openings. Showing the same sheet again does not open a new one, and
    counting openings would give 3 boxes for a single errand."""
    got = V.sheet_instances([_ev("results", src="worker:t1")] * 3)
    assert got["n_sheets"] == 1
    assert got["n_opens"] == 3
    assert got["n_errands"] == 1
    assert got["shared"] is False


# ── what it must return when the component exists ────────────────────────────────────────────────────────
def test_two_instances_are_two_sheets_and_carry_their_errand():
    got = V.sheet_instances([_ev("results::c1", src="worker:t1"), _ev("results::c2", src="worker:t2")])
    assert got["n_sheets"] == 2
    assert got["ids"] == ["results::c1", "results::c2"]
    assert got["n_errands"] == 2
    assert got["shared"] is False


def test_a_finished_sheet_is_not_reused_by_the_next_errand():
    """The second half of the rule: closed sheet + new errand = NEW box, never the previous one."""
    got = V.sheet_instances([_ev("results::c1", src="worker:t1"),
                             _ev("results::c1", label="close"),
                             _ev("results::c2", src="worker:t2")])
    assert got["n_sheets"] == 2
    assert got["n_closes"] == 1
    assert got["shared"] is False


# ── counterweights: what it must NOT count ──────────────────────────────────────────────────────────────
def test_other_widgets_are_not_sheets():
    """SENSITIVITY, and this is the side on which this reader overcounts: `navegador::t3` contains `::` and is
    part of the SAME flow. A wrongly matched prefix would turn every browser tab into a sheet."""
    got = V.sheet_instances([_ev("navegador::t3", src="worker:t1"), _ev("results", src="worker:t1"),
                             _ev("resultados-viejos", src="worker:t2")])
    assert got["ids"] == ["results"]
    assert got["n_sheets"] == 1


def test_an_errand_with_no_src_does_not_invent_one():
    """Without `src` there is no way to know which errand the opening came from, and an invented errand is what
    would make ONE search appear to be two sharing a box—the reported defect in reverse."""
    got = V.sheet_instances([_ev("results"), _ev("results")])
    assert got["n_errands"] == 0
    assert got["shared"] is False


def test_a_stream_with_no_widget_events_says_nothing():
    got = V.sheet_instances([{"payload": '{"cat": "worker", "label": "start"}'}, "no soy un dict"])
    # The entire SHAPE is intentional: if a new key appears, this case reports it instead of letting a reader
    # treat it as `None`. V2-292 added the three for “written but never opened”, and their absence must continue
    # to mean “there was nothing to count”, not “I did not look”.
    assert got == {"n_sheets": 0, "ids": [], "n_opens": 0, "n_errands": 0, "srcs": [], "shared": False,
                   "n_closes": 0, "written_ids": [], "unseen_ids": [], "n_unseen": 0}


# ── the reader travels in the mechanism report, which is what the judge reads ───────────────────────────
def test_the_reader_reaches_the_mechanism_report(monkeypatch):
    monkeypatch.setattr(V, "results_sheet", lambda ids=None: {"read": False, "n_items": 0, "titles": [],
                                                     "n_sources": 0})
    monkeypatch.setattr(V, "find_navegador_task_id", lambda _e: "")
    mech = V.mechanism_report([_ev("results", src="worker:t1"), _ev("results", src="worker:t2")], [])
    assert mech["sheet_instances"]["shared"] is True


def test_the_report_names_the_shared_box(tmp_path):
    """The report that is READ has to say it: whoever fixes it cannot read a fact that exists only in the JSON."""
    from tests.use_cases.e2e.agent import report as reportmod
    mech = {"sheet_instances": {"n_sheets": 1, "ids": ["results"], "n_opens": 2, "n_errands": 2,
                                "srcs": ["worker:t1", "worker:t2"], "shared": True, "n_closes": 0}}
    md = reportmod.build([{"scenario": "x", "tier": 4, "channel": "probe",
                           "run": {"mechanism_report": mech, "transcript": []},
                           "verdict": {"scores": {}, "overall": 3, "findings": [], "improvements": []}}],
                         "stamp", tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "hojas de resultados ABIERTAS: 1 caja(s) para 2 encargo(s)" in text
    assert "DOS ENCARGOS COMPARTIERON CAJA" in text


def test_the_judge_is_told_it_is_a_mechanism_fact_not_a_confused_agent():
    from tests.use_cases.e2e.agent import judge as J
    facts = J.mechanism_facts({"families_observed": ["worker"],
                               "sheet_instances": {"n_sheets": 1, "n_errands": 2, "shared": True}})
    assert "COMPARTIERON UNA SOLA HOJA" in facts
    assert "no lo cuentes como que zaelar se" in facts


# ── the scenario ────────────────────────────────────────────────────────────────────────────────────────
def test_the_scenario_asks_for_the_ambiguous_close():
    """Without the ambiguous instruction, the case would measure concurrency and nothing else—the closing IS half of the errand."""
    s = SC.BY_ID["two-searches-two-sheets"]
    assert s.concurrent_tasks == 2
    assert "cierra los resultados" in s.persona_brief
    assert "sheet_instances" in s.success_checks
    assert "preguntar" in s.success_checks.lower()
