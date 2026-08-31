"""An action that the turn DECIDED and the system dropped must reach the judge.

It is the difference between the two diagnoses that look identical in a transcript: “the agent did not
try” and “the agent tried and the action was dropped.” Getting this wrong cost three days — V2-133 opened
eight cases of “zaelar narrates progress that does not happen” when FlashBrain HAD called
`escalate_to_slowbrain` and its arguments arrived truncated (V2-171). A judge that cannot see this cannot
distinguish them, so it chooses the one that reads worse.

All tests pin down the REAL SHAPE of the event, which is where this breaks silently: `observer.emit`
does `ev.update(extra)`, meaning that `extra` is FLATTENED into the payload, and the payload arrives as a
JSON STRING from the observability API. A reader looking for `e["extra"]["tool"]` finds nothing and reports
“zero dropped actions,” which is indistinguishable from a healthy run.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import verify as V


def _real_event(tool: str = "show_widget", reason: str = "cortada por el tope de tokens",
                finish: str = "length") -> dict:
    """An event exactly as returned by `/api/observability/events`, not as emitted in-process."""
    return {"kind": "tool_dropped", "cat": "flash",
            "payload": json.dumps({"kind": "tool_dropped", "label": "⚠️ acción descartada",
                                   "text": f"{tool}: {reason}", "cat": "flash",
                                   "tool": tool, "reason": reason, "finish_reason": finish})}


def test_reads_the_shape_the_observability_api_actually_returns():
    got = V.dropped_actions([_real_event()])
    assert got == [{"tool": "show_widget", "reason": "cortada por el tope de tokens",
                    "finish_reason": "length"}]


def test_and_the_two_other_shapes_read_the_same():
    """Nested under `extra` and in-process: the same fact cannot depend on how the event arrived."""
    nested = [{"kind": "tool_dropped", "payload": {"extra": {"tool": "a", "reason": "b"}}}]
    inproc = [{"kind": "tool_dropped", "extra": {"tool": "a", "reason": "b"}}]
    assert V.dropped_actions(nested)[0]["tool"] == "a"
    assert V.dropped_actions(inproc)[0]["tool"] == "a"


def test_an_unrelated_event_is_not_a_dropped_action():
    """The sensitivity half: without this, “reads the drops” and “declares everything a drop” both pass."""
    assert V.dropped_actions([{"kind": "brain", "payload": "{}"},
                              {"kind": "search", "payload": json.dumps({"tool": "web_search"})}]) == []


def test_a_broken_payload_does_not_take_the_run_down():
    """Fail-open: this is evidence collection for the judge, never a gate that can bring down a run."""
    assert V.dropped_actions([{"kind": "tool_dropped", "payload": "no-es-json{{"}]) == [
        {"tool": "", "reason": "", "finish_reason": ""}]
    assert V.dropped_actions([]) == []


def test_it_reaches_the_mechanism_report_and_the_judge():
    """The helper being correct is useless if the report does not carry it: this is the failure where “the
    truth exists and does not reach the place where the decision is made,” which has already recurred in
    V2-145/V2-150 and V2-171."""
    rep = V.mechanism_report([_real_event()], expected_signals=[])
    assert rep["dropped_actions"] == [{"tool": "show_widget",
                                       "reason": "cortada por el tope de tokens",
                                       "finish_reason": "length"}]

    from tests.use_cases.e2e.agent.judge import mechanism_facts
    txt = mechanism_facts(rep)
    assert "ACCIÓN(ES) QUE ZAELAR SÍ DECIDIÓ" in txt
    assert "show_widget" in txt
    assert "no acuses a zaelar de no intentarlo" in txt


def test_and_says_nothing_when_no_action_was_dropped():
    from tests.use_cases.e2e.agent.judge import mechanism_facts
    rep = V.mechanism_report([{"kind": "brain", "payload": "{}"}], expected_signals=[])
    assert rep["dropped_actions"] == []
    assert "ACCIÓN(ES) QUE ZAELAR SÍ DECIDIÓ" not in mechanism_facts(rep)
