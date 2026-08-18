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
def test_derivation_covers_the_whole_catalog_across_all_seven_tiers():
    """Every case is runnable now, including the ones whose OUTCOME lands days later (tier 5) or needs a
    capability that does not exist (tiers 6-7). What makes that honest is `_HORIZON`, not optimism: it moves
    the bar to what a conversation can prove — a durable trigger for tier 5, a plain "I can't reach them" for
    tiers 6-7 — so nothing gets a green tick for something untested."""
    from tests.use_cases import cases_data as CD
    from tests.use_cases.e2e.agent import derived as D
    cases = D.derivable()
    assert {c.tier for c in cases} == {1, 2, 3, 4, 5, 6, 7}
    assert len(cases) == len(CD.CASES), "no case may be silently dropped from the walk"


def test_every_tier_past_the_conversation_horizon_declares_what_to_grade_instead():
    """The guard on the loophole. A blocked case is admitted ONLY because its tier says what to measure in
    place of the outcome; without that entry it would be a green tick on nothing. If a future tier gets cases
    that outlive the conversation, this fails until someone writes its horizon."""
    from tests.use_cases.e2e.agent import derived as D
    for case in D.derivable():
        if case.status == "blocked":
            assert case.tier in D._HORIZON, f"{case.id} is blocked with no horizon to grade instead"
        scn = D.derive(case)
        if case.tier in D._HORIZON:
            assert "HORIZONTE DE ESTE CASO" in scn.success_checks


def test_the_agent_to_agent_cases_answer_about_the_right_friend():
    """ES and US name a different friend (Pedro/Alex, Marta/Jordan). Aliasing the US id to the ES profile
    would hand a US persona answers about Marta — the kind of quiet contradiction that reads as an agent
    failure in the transcript when it is really the harness misinforming its own tester."""
    from tests.use_cases.e2e.agent import derived as D
    assert "Alex" in D.PROFILES["coordinate-dinner-with-alex"].success_extra
    assert "Marta" not in D.PROFILES["coordinate-dinner-with-alex"].success_extra
    assert "Jordan" in D.PROFILES["split-airbnb-with-jordan"].success_extra
    assert "Marta" not in D.PROFILES["split-airbnb-with-jordan"].success_extra


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


# ── initiative filing (initiative.py) ─────────────────────────────────────────────────────────────────────
def _result(overall=2, scenario_id="unit-mf"):
    return {"scenario": scenario_id, "tier": 4,
            "verdict": {"overall": overall, "scores": {"mecanismo": 1, "naturalidad": 4},
                        "veredicto": "no coordina", "findings": [], "improvements": []},
            "run": {"transcript": [{"who": "tester", "text": "hola"}],
                    "mechanism_report": {"families_observed": ["flash"], "missing_signals": ["worker"],
                                         "task_registry": {"max_concurrent": 1, "distinct_tasks_seen": 3,
                                                           "distinct_kinds": ["web"]}},
                    "watchdog_log": [{"health": "stuck", "action": "nudge", "reason": "sin tareas vivas"}]}}


def _isolate(monkeypatch, tmp_path):
    from tests.use_cases.e2e.agent import initiative as I
    monkeypatch.setattr(I, "INITIATIVES", tmp_path / "initiatives")
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    (tmp_path / "initiatives").mkdir()
    (tmp_path / "modules").mkdir()
    return I


def test_filing_creates_one_initiative_and_one_fix_task(monkeypatch, tmp_path):
    I = _isolate(monkeypatch, tmp_path)
    out = I.file_failure(_result(), scenario=_scn(), sandboxed=True)
    assert out["created"] is True and out["round"] == 1
    body = out["initiative"].read_text(encoding="utf-8")
    # the handoff contract has to be IN the file — that is the whole point of filing it
    assert "HANDOFF" in body and "tarea de VERIFICACIÓN" in body
    assert "--sandbox" in body                       # a reproduce command the next agent can paste
    assert "máximo simultáneo **1**" in body         # the measured evidence, not a summary of it
    assert "sin tareas vivas" in body                # watchdog findings carried over
    task = out["task"].read_text(encoding="utf-8")
    assert "initiative: V2-" in task and "status: next" in task
    assert "T<siguiente>-uc-" in task                # tells the fixer exactly how to hand it back


def test_filing_never_marks_an_initiative_delivered(monkeypatch, tmp_path):
    """`delivered` is load-bearing: test_roadmap_closure.py forces any delivered initiative to be cited in
    engine/CLAUDE.md, so filing a fresh bug as delivered would turn the suite red."""
    I = _isolate(monkeypatch, tmp_path)
    out = I.file_failure(_result(), scenario=_scn(), sandboxed=True)
    assert "status: open" in out["initiative"].read_text(encoding="utf-8")
    assert "delivered" not in out["initiative"].read_text(encoding="utf-8").split("---")[1]


def test_re_testing_appends_a_round_instead_of_opening_a_second_initiative(monkeypatch, tmp_path):
    """One workspace per use case ("corregirlos hasta el final"), not a pile of duplicates."""
    I = _isolate(monkeypatch, tmp_path)
    first = I.file_failure(_result(), scenario=_scn(), sandboxed=True)
    second = I.file_failure(_result(), scenario=_scn(), sandboxed=True)
    assert second["created"] is False and second["round"] == 2
    assert second["initiative"] == first["initiative"]
    assert len(list((tmp_path / "initiatives").glob("*.md"))) == 1
    assert "## Ronda 2" in second["initiative"].read_text(encoding="utf-8")


def test_initiative_number_is_read_from_disk_not_assumed(monkeypatch, tmp_path):
    """V2-114 is currently double-booked by two other sessions and the closure test is red because of it;
    allocating from a fresh listing at write time is the only safe way when several sessions share the repo."""
    I = _isolate(monkeypatch, tmp_path)
    (tmp_path / "initiatives" / "V2-200-something-else.md").write_text("x", encoding="utf-8")
    out = I.file_failure(_result(), scenario=_scn(), sandboxed=True)
    assert out["initiative"].name.startswith("V2-201-uc-")


def test_pending_verifications_picks_up_the_fixers_handoff(monkeypatch, tmp_path):
    I = _isolate(monkeypatch, tmp_path)
    d = tmp_path / "modules" / "nucleo" / "tasks"
    d.mkdir(parents=True)
    (d / "T400-uc-my-case-verify.md").write_text(
        "---\nid: T400\nstatus: next\ninitiative: V2-118\n---\n\nlisto para re-probar\n", encoding="utf-8")
    (d / "T401-uc-other-case-verify.md").write_text(
        "---\nid: T401\nstatus: done\ninitiative: V2-119\n---\n", encoding="utf-8")
    pend = I.pending_verifications()
    assert [p["slug"] for p in pend] == ["my-case"]   # only status:next is a live handoff


def test_a_pending_slug_resolves_back_to_the_runnable_scenario_id(monkeypatch, tmp_path):
    """The task filename carries a kebab SLUG, the runner needs the scenario ID — and `__` collapses in the
    slug, so reversing the string is lossy. Resolution goes through the live registry instead."""
    I = _isolate(monkeypatch, tmp_path)
    d = tmp_path / "modules" / "nucleo" / "tasks"
    d.mkdir(parents=True)
    slug = I._slug("quick-fact-opening-hours__es")
    (d / f"T402-uc-{slug}-verify.md").write_text("---\nid: T402\nstatus: next\n---\n", encoding="utf-8")
    out = I.scenarios_awaiting_verification({"quick-fact-opening-hours__es": object()})
    assert out[0]["scenario"] == "quick-fact-opening-hours__es"


def test_a_renamed_scenario_is_reported_not_swallowed(monkeypatch, tmp_path):
    """A verify task whose scenario no longer exists must surface. Skipping it in silence leaves the fixing
    agent waiting on a re-test that will never run — the failure mode the whole handoff exists to prevent."""
    I = _isolate(monkeypatch, tmp_path)
    d = tmp_path / "modules" / "nucleo" / "tasks"
    d.mkdir(parents=True)
    (d / "T403-uc-a-case-that-moved-verify.md").write_text("---\nid: T403\nstatus: next\n---\n",
                                                           encoding="utf-8")
    out = I.scenarios_awaiting_verification({"something-else": object()})
    assert out and out[0]["scenario"] is None and out[0]["slug"] == "a-case-that-moved"


def test_closing_a_verification_stops_it_matching_again(monkeypatch, tmp_path):
    """Closing must happen whether the re-test passed or failed. Left as `next`, every later --verify batch
    re-runs the same case with nobody having changed anything in between: a loop that cannot converge."""
    I = _isolate(monkeypatch, tmp_path)
    d = tmp_path / "modules" / "nucleo" / "tasks"
    d.mkdir(parents=True)
    task = d / "T404-uc-my-case-verify.md"
    task.write_text("---\nid: T404\nstatus: next\nupdated: 2026-01-01\n---\n\nlisto\n", encoding="utf-8")
    assert I.close_verification(task, round_no=2) is True
    body = task.read_text(encoding="utf-8")
    assert "status: done" in body and "status: next" not in body
    assert "ronda 2" in body                      # points at where the evidence lives
    assert I.pending_verifications() == []
    assert I.close_verification(d / "nope.md") is False   # fails open, never raises into a batch


def test_filing_fails_open_and_never_takes_down_a_batch(monkeypatch, tmp_path):
    I = _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(I, "_next_initiative_number", lambda: (_ for _ in ()).throw(OSError("disk")))
    out = I.file_failure(_result(), scenario=_scn(), sandboxed=True)
    assert "error" in out          # reported, not raised — the verdict is already earned


# ── search-layer confound (verify.search_health + judge/initiative wiring) ─────────────────────────────────
def test_a_dead_search_layer_is_detected_from_its_own_reply():
    """The signature is in the search tool's verbatim reply, which is what `kind="search"` events carry. This
    is the exact text a real run produced: the worker's WebSearch answering 429 Weekly/Monthly Limit
    Exhausted while a scenario was being graded on whether it looked anything up."""
    from tests.use_cases.e2e.agent import verify as V
    ev = [{"kind": "search", "label": "🌐 web", "text": "web_search Casa Lucio reservas"},
          {"kind": "search", "label": "🌐 web ↩",
           "text": 'MCP error -429: {"code":"1310","message":"Weekly/Monthly Limit Exhausted."}'},
          {"kind": "search", "label": "🌐 web ↩", "text": "google: bloqueado (captcha/tráfico inusual)"},
          {"kind": "flash", "text": "no es una búsqueda"}]
    h = V.search_health(ev)
    assert h["degraded"] is True and h["n_search_events"] == 3
    assert dict(h["reasons"]) == {"quota_exhausted": 1, "blocked": 1}


def test_a_search_that_merely_found_nothing_is_NOT_a_degraded_layer():
    """The counterweight, and the reason this can't just look for 'no results'. A working search that returns
    nothing is a legitimate outcome the agent must handle — calling that an environment fault would excuse the
    real defect of giving up, which is the opposite of what this is for."""
    from tests.use_cases.e2e.agent import verify as V
    ev = [{"kind": "search", "label": "🌐 web", "text": "web_search guitarra zurda infantil"},
          {"kind": "search", "label": "🌐 web ↩", "text": "0 resultados para esa consulta"}]
    assert V.search_health(ev)["degraded"] is False


def test_the_confound_reaches_the_judge_before_it_reasons():
    """Annotating the verdict afterwards is what the first batch needed by hand and it does not scale — the
    note has to reach the model that is about to decide whether 'answered without searching' is a defect."""
    from tests.use_cases.e2e.agent import judge as J
    assert "{why}" in J.SEARCH_DEGRADED_NOTE
    note = J.SEARCH_DEGRADED_NOTE.format(why="quota_exhausted ×3")
    assert "NO penalices" in note and "SÍ penaliza" in note   # both halves, or it becomes an excuse


def test_the_confound_never_rewrites_the_verdict_into_INFRA():
    """A degraded environment must not launder a real failure. An agent that invents facts while search is
    down is still inventing facts — and that is the more serious half, so it stays a FAIL on the scoreboard."""
    from tests.use_cases.e2e.agent import status as S
    r = {"scenario": "x", "tier": 2,
         "run": {"mechanism_report": {"search_health": {"degraded": True,
                                                        "reasons": [("quota_exhausted", 2)]}}},
         "verdict": {"overall": 1, "scores": {}, "veredicto": "inventó el resultado"}}
    assert S._state(1, r) == "FAIL"


def test_the_board_shows_how_much_of_the_catalog_is_still_UNRUN(tmp_path, monkeypatch):
    """An unrun case is not a passing one. Without the denominator, "1 passing · 4 failing" reads like the
    whole answer to "which use cases work?" while 114 cases nobody has run go unmentioned."""
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    status.record([{"scenario": "restaurant-tonight-madrid", "tier": 1,
                    "verdict": {"overall": 5, "scores": {}, "veredicto": "ok"},
                    "run": {"mechanism_report": {}}}], sandboxed=True)
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "Catalog coverage — 1 of" in board
    assert "never run)" in board
    assert "| tier | locale | run | of | passing |" in board


def test_the_board_names_the_workspace_of_each_failing_case(tmp_path, monkeypatch):
    """The initiative IS the workspace for a case, but it sits among 100+ others in a gitignored folder — an
    agent handed only "quick-fact is failing" would need the naming convention to find anything. Paths only,
    never content: the case id is already public, the transcript inside the initiative is not."""
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    status.record([{"scenario": "bad", "tier": 1, "verdict": {"overall": 1, "scores": {}, "veredicto": "no"},
                    "run": {"mechanism_report": {}}},
                   {"scenario": "good", "tier": 1, "verdict": {"overall": 5, "scores": {}, "veredicto": "ok"},
                    "run": {"mechanism_report": {}}}], sandboxed=True)
    status.attach_workspaces({"bad": {"initiative": ".meshkore/roadmap/initiatives/V2-999-uc-bad.md",
                                     "task": ".meshkore/modules/nucleo/tasks/T999-uc-bad-fix.md"},
                              "good": {"initiative": "never-filed.md", "task": ""}})
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "V2-999-uc-bad.md" in board and "T999-uc-bad-fix.md" in board
    assert "never-filed.md" not in board      # a PASSING case has no workspace to point at
    status.attach_workspaces({})              # no-op, must not wipe what is there
    assert "V2-999-uc-bad.md" in (tmp_path / "STATUS.md").read_text(encoding="utf-8")


def test_a_re_run_keeps_the_workspace_pointer(tmp_path, monkeypatch):
    """Every other field here is per-round and rightly replaced; the initiative is the case's home for its
    whole life. Losing it on round 2 is exactly backwards — that is the round that needs it most."""
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    res = [{"scenario": "bad", "tier": 1, "verdict": {"overall": 1, "scores": {}, "veredicto": "no"},
            "run": {"mechanism_report": {}}}]
    status.record(res, sandboxed=True)
    status.attach_workspaces({"bad": {"initiative": "ini.md", "task": "t.md"}})
    status.record(res, sandboxed=True)                     # round 2
    assert status.load()["scenarios"]["bad"]["workspace"]["initiative"] == "ini.md"


# ── the harness must not die on a legal-but-different reply shape ──────────────────────────────────────────
def test_a_list_shaped_reply_does_not_kill_the_scenario():
    """`buy-known-product__es` was lost to `'list' object has no attribute 'strip'`: the broker returned
    OpenAI's structured content form. Both shapes are legal and the provider picks, so the caller can't be the
    place that knows. Non-text parts are DROPPED, not stringified — a `str(dict)` of an image part pasted into
    the tester's next utterance is worse than saying nothing."""
    from tests.use_cases.e2e.agent import llm as L
    assert L._as_text("plain") == "plain"
    assert L._as_text([{"type": "text", "text": "hola "}, {"type": "text", "text": "mundo"}]) == "hola mundo"
    assert L._as_text([{"type": "image_url", "image_url": {"url": "x"}}]) == ""
    assert L._as_text(None) == ""
