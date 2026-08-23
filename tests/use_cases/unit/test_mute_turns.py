"""An EMPTY turn is a channel breakdown, not an agent refusing to help.

The text channel resolves its provider through `spec_from_config()` and never consults the failover chain, so
with the titular model out of funds the turns come back mute (the engine team pointed this out on 2026-08-20).
There were already rounds with `(sin respuesta)` — `renew-gym-membership__es` among them — scored as if zaelar
had ignored the user. It is the same mistake `search_health` exists to prevent: an environment confound passing
for a product defect.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import judge as J


def test_the_judge_is_told_a_mute_turn_is_the_CHANNEL():
    txt = J.mechanism_facts({"mute_turns": {"n": 2, "turns": [3, 5]}})
    assert "AVERÍA DEL CANAL, NO DEL AGENTE" in txt
    assert "2 turno(s)" in txt and "[3, 5]" in txt
    assert "No puntúes un turno vacío" in txt


def test_and_told_what_to_do_INSTEAD():
    """Without the positive instruction the notice only forbids, and the model is left with no criterion."""
    txt = J.mechanism_facts({"mute_turns": {"n": 1, "turns": [0]}})
    assert "Juzga solo los turnos que SÍ tienen texto" in txt


def test_a_run_with_no_mute_turns_gets_no_excuse():
    """Sensitivity: if the notice always appeared, the judge would forgive the product's genuine silence."""
    txt = J.mechanism_facts({"families_observed": ["flash"]})
    assert "AVERÍA DEL CANAL" not in txt
    txt2 = J.mechanism_facts({"mute_turns": {"n": 0, "turns": []}})
    assert "AVERÍA DEL CANAL" not in txt2


def test_the_runner_COUNTS_them(monkeypatch):
    """The notice existing is useless if nobody counts the empty turns. This drives a real run with two empty
    replies and checks they reach the report the judge sees."""
    from tests.use_cases.e2e.agent import run as R
    from tests.use_cases.e2e.agent import scenarios as SC

    seen: dict = {}
    replies = iter(["", "", "por fin hablo"])
    monkeypatch.setattr(R.probe_client, "say",
                        lambda t, s, **k: {"reply": next(replies, ""), "trace": "t"})
    monkeypatch.setattr(R.probe_client, "reset", lambda s: {})
    monkeypatch.setattr(R.probe_client, "current_session_id", lambda: "s")
    monkeypatch.setattr(R.probe_client, "session_events", lambda sid: [])
    monkeypatch.setattr(R.probe_client, "scheduled_jobs", lambda: [])
    monkeypatch.setattr(R.probe_client, "widget_rows", lambda wid, key: [])
    monkeypatch.setattr(R.verifymod, "mechanism_report", lambda *a, **k: {})
    monkeypatch.setattr(R.watchdogmod, "evaluate", lambda *a, **k: {"action": "continue", "health": "flowing",
                                                                   "reason": ""})
    monkeypatch.setattr(R.judgemod, "judge",
                        lambda scn, run: seen.setdefault("mech", run["mechanism_report"]) or {})
    monkeypatch.setattr(R.llmmod, "drive_model", lambda: "m")

    class _D:
        def __init__(self, scn, persona_name=""): self.done = False
        def opening(self): return "hola"
        def hears(self, t): pass
        def reply(self, nudge=""): return "sigo"
    monkeypatch.setattr(R.drivermod, "Driver", _D)

    R._run_scenario(SC.UseCaseScenario(id="x", locale="es", tier=1, persona_brief="p",
                                       opening_line="o", success_checks="s", turns=3))
    assert seen["mech"].get("mute_turns", {}).get("n") == 2, \
        "the runner is not counting the empty turns"
