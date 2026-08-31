"""A case is not closed merely for receiving a good score: the ENTIRE audit must have been read.

Operator rule, 2026-08-20: *“do not go marking them as closed until they complete successfully and you
check every step, event, and internal process, reading their entire observability audit”*.

What existed measured FAMILIES: did `worker` appear, did `widget` appear? That is not the same question. The
real run on 2026-08-20 at 10:00 had both expected families present **and** an event with `is_error: true` in
a worker step —*“Exit code 2, I cannot read the sources.json payload”*— that did not appear in the mechanism
report, the judge's prompt, or the operator's report. By the old criterion, the mechanism was
correct.

The failure preserved here is the costly one: closing a case archives a MEASURED defect as though it did not
exist, and nothing turns red.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import status as ST, verify as V


def _ev(**kw):
    base = {"cat": "worker", "kind": "task", "label": "· paso", "text": "", "rel_ms": 1000}
    base.update(kw)
    return base


def test_an_internal_error_is_surfaced_as_a_fact():
    a = V.audit([_ev(), _ev(label="· paso ⚠️ error", is_error=True, text="Exit code 2 no puedo leer sources.json",
                     span="worker:1")])
    assert not a["clean"]
    clases = [x["clase"] for x in a["anomalies"]]
    assert "error_interno" in clases
    assert all(x["certeza"] == "hecho" for x in a["anomalies"] if x["clase"] == "error_interno"), (
        "un `is_error` del propio sistema no es una interpretación")


def test_a_run_with_no_internal_error_is_clean():
    """Half of the sensitivity check: without this, “audits” and “always finds something” pass alike, and an audit
    that never comes back clean blocks every case forever."""
    a = V.audit([_ev(evidence=True), _ev(rel_ms=2000, evidence=True)], ["worker"])
    assert a["clean"], a["anomalies"]


def test_evidence_and_the_tools_that_really_ran_are_counted():
    """The only thing that can make a claim about the world true is the world having answered."""
    a = V.audit([_ev(evidence=True, tool="WebFetch"), _ev(evidence=True, tool="WebFetch"),
                 _ev(tool="Bash")])
    assert a["n_evidence"] == 2
    assert a["tools_run"] == {"WebFetch": 2, "Bash": 1}


def test_zero_evidence_with_a_worker_expected_is_an_anomaly():
    a = V.audit([_ev(), _ev(rel_ms=2000)], ["Brain Workers"])
    assert "sin_evidencia_externa" in [x["clase"] for x in a["anomalies"]], (
        "cero eventos con evidencia y un worker esperado: nada volvió del mundo exterior")


def test_but_zero_evidence_is_NOT_an_anomaly_for_a_conversational_case():
    a = V.audit([_ev(cat="flash"), _ev(cat="flash", rel_ms=2000)], ["FlashBrain"])
    assert "sin_evidencia_externa" not in [x["clase"] for x in a["anomalies"]]


def test_a_long_silence_is_measured_not_judged():
    a = V.audit([_ev(rel_ms=0), _ev(rel_ms=95_000)])
    sil = [x for x in a["anomalies"] if x["clase"] == "silencio"]
    assert sil and sil[0]["certeza"] == "medida"


def test_the_anomalies_travel_in_the_LEDGER_so_the_tick_can_act_on_them(tmp_path, monkeypatch):
    """The tick decides closure in the PARENT process, where the run dict no longer exists. If this does not travel in the
    marker, the closure gate has nothing to decide with and everything passes just as before.

    ⚠️ Against a TEMPORARY marker. The first version called `record` directly and wrote a fake scenario
    (“x”) to the campaign's REAL marker: a unit test cannot touch the board that the loop is using to decide
    what to re-test.
    """
    monkeypatch.setattr(ST, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(ST, "BOARD_PATH", tmp_path / "STATUS.md")
    result = {"scenario": "x", "tier": 1,
              "run": {"transcript": [], "mechanism_report": {
                  "audit": {"anomalies": [{"clase": "error_interno", "certeza": "hecho", "que": "boom"}]}}},
              "verdict": {"overall": 5, "scores": {}, "veredicto": "ok"}}
    entry = ST.record([result], sandboxed=True)["scenarios"]["x"]
    assert entry["audit_anomalies"] == [{"clase": "error_interno", "certeza": "hecho", "que": "boom"}]
    assert entry["state"] == "PASS", "la nota del juez es la nota; la auditoría no la reescribe, frena el CIERRE"


def test_the_audit_reads_the_shape_the_API_actually_serves():
    """The most costly failure this audit has had, and it lasted an hour.

    `observer.emit` does `ev.update(extra)`, so the fields land FLAT in the payload — and the payload arrives
    from the observability API as a JSON STRING. The first version of `audit` read `e.get("evidence")`
    directly, so it always returned ZERO evidence, hence `sin_evidencia_externa` in every case
    with an expected worker.

    On 2026-08-20 at 12:2x that assigned the anomaly “the outside world brought nothing” to THREE different
    cases (`find-theatre`, `restaurant`, `cheapest-monitor`) — while the timeline for that same batch had **60
    events with `evidence`, 26 of them from the browser**. It was about to be handed to the fixing agent
    as a measured fact. An audit that INVENTS an anomaly is worse than having none: it sends someone to look for
    a defect that is mine.

    And the warning was written down: the docstring of `_fields` says it literally. Documenting it is not enough.
    """
    import json

    from tests.use_cases.e2e.agent import verify as V

    api_shape = [
        {"cat": "worker", "kind": "navegador",
         "payload": json.dumps({"label": "🏁 hito", "evidence": True, "rel_ms": 100, "span": "worker:1"})},
        {"cat": "worker", "kind": "task",
         "payload": json.dumps({"label": "paso", "is_error": True, "text": "boom", "tool": "Bash",
                                "rel_ms": 200, "span": "worker:1"})},
    ]
    a = V.audit(api_shape, ["Brain Workers"])

    assert a["n_evidence"] == 1, "los campos vienen dentro del payload como cadena JSON"
    assert len(a["errors"]) == 1 and "boom" in a["errors"][0]["text"]
    assert a["tools_run"] == {"Bash": 1}
    assert "sin_evidencia_externa" not in [x["clase"] for x in a["anomalies"]], (
        "esta es la anomalía inventada: había evidencia y el lector no la veía")
    assert a["spans"]["worker:1"]["errors"] == 1, "el span también se lee del payload"


def test_an_agenda_write_is_VISIBLE_in_the_mechanism_report():
    """Returned by the fixing agent on 2026-08-20, and it was right.

    The criterion for `remember-and-remind-deadline` literally says “judge by … calendar data-ops”, and the
    mechanism report contained NONE: only families (`widget` appears, but not WHICH widget or what was done)
    and the `scheduled_jobs` block, which is for CRONS. Thus a finding such as “neither the calendar event
    nor the trigger exists” relied, for half of the calendar behavior, on a reader that does not cover calendars.
    In its reproduction, the appointment WAS written.

    Same class as the `evidence` failure a few hours earlier: a reader that looks where it is not does not fail;
    it ANSWERS — and answers with an absence, which is the most credible and damaging answer.
    """
    from tests.use_cases.e2e.agent import verify as V

    evs = [{"cat": "widget", "kind": "widget", "label": "data", "id": "agenda::ev1"},
           {"cat": "widget", "kind": "widget", "label": "show", "id": "agenda::ev1"},
           {"cat": "widget", "kind": "widget", "label": "data", "id": "navegador::t2"},
           {"cat": "flash", "kind": "trace", "label": "turno"}]
    ops = V.widget_ops(evs)
    assert ops["agenda"] == {"data": 1, "show": 1}, "una escritura en agenda tiene que ser VISIBLE y contable"
    assert ops["navegador"] == {"data": 1}
    assert "flash" not in ops, "solo la familia widget"


def test_the_judge_is_told_not_to_infer_a_missing_appointment_from_the_crons():
    """The half that prevents the false finding: durable triggers are CRONS; the appointment is a data-op. Without
    being told this, the judge again concludes “there is no appointment” by reading a block that does not discuss appointments."""
    from tests.use_cases.e2e.agent import judge as J

    prose = J.mechanism_facts({"families_observed": ["widget"], "expected_signals": ["memory"],
                               "widget_ops": {"agenda": {"data": 1}},
                               "scheduled_jobs": {"readable": True, "created": []}})
    assert "agenda (data×1)" in prose, "la escritura de agenda tiene que llegarle en PROSA, no solo en el JSON"
    assert "CRONS, no de agendas" in prose


def test_and_the_report_actually_WIRES_it():
    """The missing half, and the same gap I already made with the audit: the two tests above call
    `widget_ops` directly or pass the already-built dict to the judge, so both PASS even if
    `mechanism_report` stops including it (confirmed: replacing the call with `{}` does not make them red).
    A constant can remain unwired; what must be asserted is what the consumer RECEIVES.
    """
    from tests.use_cases.e2e.agent import verify as V

    mech = V.mechanism_report([{"cat": "widget", "kind": "widget", "label": "data", "id": "agenda::ev1"}],
                              ["memory"])
    assert mech.get("widget_ops") == {"agenda": {"data": 1}}, (
        "el informe no lleva las operaciones de widget: el juez vuelve a quedarse sin ver la cita")
