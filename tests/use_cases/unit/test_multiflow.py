"""Deterministic tests for the MULTI-FLOW machinery (2026-08-18, operator request: a use case where several
tasks run at once and the agent has to work out which message belongs to which).

The scenario itself is non-deterministic by design, but the three pieces that make it JUDGEABLE are not:
the live-concurrency tracker, the judge's conditional rubric, and the scoreboard's state classification.
Those are what these tests pin down — a multi-flow run whose concurrency measurement or rubric is wrong
produces a confident-looking verdict about nothing.
"""
from __future__ import annotations

import json

from tests.use_cases.e2e.agent import judge as judgemod
from tests.use_cases.e2e.agent import scenarios, status, verify


def _scn(**kw):
    base = dict(id="unit-mf", locale="es", tier=4, persona_brief="x", opening_line="y", success_checks="z")
    base.update(kw)
    return scenarios.UseCaseScenario(**base)


# ── ConcurrencyTracker ────────────────────────────────────────────────────────────────────────────────────
def test_tracker_records_peak_concurrency_not_just_the_last_sample(monkeypatch):
    """The number that matters is the PEAK: tasks finish at different times, so the final sample routinely
    shows fewer than were ever really in flight together."""
    seq = [
        [{"id": "t1", "kind": "web"}],
        [{"id": "t1", "kind": "web"}, {"id": "t2", "kind": "code"}, {"id": "t3", "kind": "web"}],
        [{"id": "t3", "kind": "web"}],
    ]
    calls = iter(seq)
    monkeypatch.setattr(verify.probe_client, "live_tasks", lambda: next(calls))
    tr = verify.ConcurrencyTracker()
    for i in range(3):
        tr.sample(at_turn=i)
    rep = tr.report()
    assert rep["max_concurrent"] == 3
    assert rep["distinct_tasks_seen"] == 3
    assert rep["distinct_kinds"] == ["code", "web"]


def test_tracker_fails_open_when_the_registry_is_unreachable(monkeypatch):
    monkeypatch.setattr(verify.probe_client, "live_tasks",
                        lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    tr = verify.ConcurrencyTracker()
    tr.sample(at_turn=0)
    assert tr.report()["max_concurrent"] == 0      # no crash, just no evidence
    assert tr.hint() == ""


def test_tracker_hint_names_live_tasks_for_the_watchdog(monkeypatch):
    monkeypatch.setattr(verify.probe_client, "live_tasks",
                        lambda: [{"id": "t1", "kind": "web", "phase": "navegando", "status": "running"},
                                 {"id": "t2", "kind": "code", "phase": "", "status": "running"}])
    tr = verify.ConcurrencyTracker()
    tr.sample(at_turn=0)
    hint = tr.hint()
    assert "2 tareas VIVAS" in hint
    assert "web:navegando" in hint
    assert "code:running" in hint       # falls back to status when phase is empty


def test_mechanism_report_includes_task_registry_only_for_multiflow(monkeypatch):
    monkeypatch.setattr(verify, "poll_navegador_task", lambda *a, **k: {})
    monkeypatch.setattr(verify.probe_client, "live_tasks", lambda: [{"id": "t1", "kind": "web"}])
    plain = verify.mechanism_report([{"cat": "flash"}], [])
    assert "task_registry" not in plain

    tr = verify.ConcurrencyTracker()
    tr.sample(at_turn=0)
    multi = verify.mechanism_report([{"cat": "flash"}], [], tr)
    assert multi["task_registry"]["max_concurrent"] == 1


# ── judge: the extra dimensions exist ONLY for a multi-flow scenario ──────────────────────────────────────
def test_judge_prompt_adds_attribution_and_fluidity_for_multiflow(monkeypatch):
    captured: dict = {}

    def _spy(messages, **kw):
        captured["user"] = messages[1]["content"]
        return json.dumps({"scores": {}, "overall": 3, "findings": [], "improvements": [],
                           "veredicto": "ok"}), "stub-model"

    monkeypatch.setattr(judgemod.llm, "judge_call", _spy)

    judgemod.judge(_scn(concurrent_tasks=3), {"transcript": [], "mechanism_report": {}, "watchdog_log": []})
    assert "atribucion" in captured["user"]
    assert "fluidez" in captured["user"]
    assert "MULTI-FLUJO" in captured["user"]
    assert '"atribucion":n' in captured["user"]        # the JSON schema asked for actually includes them

    judgemod.judge(_scn(), {"transcript": [], "mechanism_report": {}, "watchdog_log": []})
    assert "atribucion" not in captured["user"]        # single-task scoring stays comparable to history
    assert "MULTI-FLUJO" not in captured["user"]


# ── scoreboard ────────────────────────────────────────────────────────────────────────────────────────────
def test_status_separates_infra_from_a_real_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    led = status.record([
        {"scenario": "good", "tier": 1, "verdict": {"overall": 5, "scores": {}, "veredicto": "listo"},
         "run": {"mechanism_report": {}}},
        {"scenario": "bad", "tier": 2, "verdict": {"overall": 2, "scores": {}, "veredicto": "no llega"},
         "run": {"mechanism_report": {}}},
        {"scenario": "broken", "tier": 2, "verdict": {"overall": None, "scores": {},
                                                       "veredicto": "INFRA: timeout"},
         "run": {"mechanism_report": {}, "crashed": "timeout"}},
    ], sandboxed=True)
    assert led["scenarios"]["good"]["state"] == "PASS"
    assert led["scenarios"]["bad"]["state"] == "FAIL"
    # A crashed harness must never be recorded as a failing use case — that is how a scoreboard starts lying.
    assert led["scenarios"]["broken"]["state"] == "INFRA"
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "1 passing · 1 failing · 1 infra" in board


def test_status_only_touches_scenarios_that_actually_ran(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    status.record([{"scenario": "a", "tier": 1, "verdict": {"overall": 5, "scores": {}, "veredicto": "ok"},
                    "run": {"mechanism_report": {}}}], sandboxed=False)
    status.record([{"scenario": "b", "tier": 1, "verdict": {"overall": 1, "scores": {}, "veredicto": "no"},
                   "run": {"mechanism_report": {}}}], sandboxed=False)
    led = status.load()
    assert led["scenarios"]["a"]["state"] == "PASS"      # a single-scenario batch didn't wipe the other
    assert led["scenarios"]["b"]["state"] == "FAIL"


def test_status_records_multiflow_concurrency(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    status.record([{"scenario": "mf", "tier": 4,
                    "verdict": {"overall": 4, "scores": {}, "veredicto": "coordina"},
                    "run": {"mechanism_report": {"task_registry": {"max_concurrent": 3,
                                                                   "distinct_kinds": ["code", "web"]}}}}],
                  sandboxed=True)
    e = status.load()["scenarios"]["mf"]
    assert e["max_concurrent"] == 3
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "Multi-flow scenarios" in board


# ── the scenario is registered and coherent ───────────────────────────────────────────────────────────────
def test_multiflow_scenario_is_registered_and_declares_its_task_count():
    s = scenarios.BY_ID["three-tasks-at-once"]
    assert s.concurrent_tasks == 3
    assert s.turns >= 12          # three tasks need room to start AND interleave
    assert "worker" in s.expected_signals and "widget" in s.expected_signals


def test_every_other_scenario_stays_single_task():
    """Guard: `concurrent_tasks` changes the runner's behavior (live registry sampling) and the judge's
    rubric, so it must never get set by accident on a single-task scenario."""
    multi = [s.id for s in scenarios.SCENARIOS if s.concurrent_tasks]
    assert multi == ["three-tasks-at-once"]


# ── derivation engine (derived.py) ────────────────────────────────────────────────────────────────────────
def test_derivation_covers_every_tier_1_to_4_case_and_nothing_else():
    """Tier 5 needs real time to pass and tiers 6-7 are blocked on unbuilt capabilities (V2-052 contacts,
    WhatsApp/Telegram send) — deriving a scenario for those would put a runnable-looking tick on something
    that cannot honestly be tested."""
    from tests.use_cases.e2e.agent import derived as D
    tiers = {c.tier for c in D.derivable()}
    assert tiers == {1, 2, 3, 4}
    assert all(c.status != "blocked" for c in D.derivable())


def test_derived_scenario_carries_the_shared_scaffolding_and_the_case_utterance():
    from tests.use_cases import cases_data as CD
    from tests.use_cases.e2e.agent import derived as D
    case = next(c for c in CD.CASES if c.id == "cancel-subscription-before-charge" and c.locale == "es")
    s = D.derive(case)
    assert s.opening_line == case.utterance
    assert case.utterance in s.persona_brief
    # the boilerplate that used to be copy-pasted into every hand-written brief
    assert "NO te despidas todavía" in s.persona_brief
    assert "No reveles" in s.persona_brief
    # this case's own programmed specifics
    assert "la mía de siempre" in s.persona_brief
    # and the judging rules a template must always carry
    assert "PREGUNTAR" in s.success_checks
    assert "IRREVERSIBLE" in s.success_checks


def test_handwritten_scenarios_are_never_shadowed_by_a_derived_one():
    """The nine hand-written briefs carry nuance a template cannot express (a deliberately empty
    expected_signals, a multi-task persona). A derived scenario replacing one silently would be a
    regression nobody would notice until a verdict got worse for no reason."""
    from tests.use_cases.e2e.agent import scenarios as SC
    reg = SC.registry()
    for hand in SC.SCENARIOS:
        assert reg[hand.id] is hand


def test_us_cases_get_an_english_brief():
    from tests.use_cases import cases_data as CD
    from tests.use_cases.e2e.agent import derived as D
    case = next(c for c in CD.CASES if c.locale == "us" and c.tier <= 4)
    assert "ENGLISH" in D.derive(case).persona_brief


def test_every_scenario_id_is_unique():
    from tests.use_cases.e2e.agent import scenarios as SC
    ids = [s.id for s in SC.all_scenarios()]
    assert len(ids) == len(set(ids))


def test_es_and_us_twins_of_a_shared_case_id_stay_distinct():
    """`cheapest-monitor` exists in both locales; a bare-id scenario for each would collide and one market
    would silently never run."""
    from tests.use_cases.e2e.agent import scenarios as SC
    ids = {s.id for s in SC.all_scenarios()}
    assert "cheapest-monitor" in ids                  # the hand-written ES one
    assert "cheapest-monitor__us" in ids              # the derived US twin
