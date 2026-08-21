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
    multi = sorted(s.id for s in scenarios.SCENARIOS if s.concurrent_tasks)
    # Inventario CERRADO, y cada uno con su motivo:
    #   · three-tasks-at-once      → se JUZGA por la coordinación de tres encargos a la vez.
    #   · two-searches-two-sheets  → mide que dos búsquedas simultáneas abran DOS hojas, y «simultáneas» es
    #     justo lo que el muestreo del registro vivo prueba: un volcado posterior enseña que existieron dos
    #     tareas, nunca que se solaparan en el tiempo.
    assert multi == ["three-tasks-at-once", "two-searches-two-sheets"]


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
    regression nobody would notice until a verdict got worse for no reason.

    Compared by CONTENT, not identity: the real-data limit is deliberately attached to hand-written scenarios
    too (`apply_data_note` returns a copy), so `is` would now fail for a reason that is not shadowing. The
    brief and the opening line are what "not shadowed" actually means."""
    from tests.use_cases.e2e.agent import dates as DT, scenarios as SC
    reg = SC.registry()
    for hand in SC.SCENARIOS:
        got = reg[hand.id]
        # Contra el texto RESUELTO: las fechas de un caso son relativas a hoy (norma del operador 2026-08-19),
        # así que el registro sustituye sus tokens. Comparar contra el crudo haría fallar este test por la
        # resolución de fechas, que no es sombreado — y el test dejaría de vigilar lo que existe para vigilar.
        assert got.opening_line == DT.resolve(hand.opening_line)
        assert got.persona_brief == DT.resolve(hand.persona_brief)
        assert got.expected_signals == hand.expected_signals
        assert got.success_checks.startswith(DT.resolve(hand.success_checks))   # only ADDED to, never replaced


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
    whole answer to "which use cases work?" while 100+ cases nobody has run go unmentioned.

    Two denominators, and the distinction is the point (operator, 2026-08-19): the SEGMENT table says how many
    cases exist at all per group, and the progress board counts only the `completable` ones — a case blocked on
    a credential is not pending work, so putting it in the progress denominator makes the walk look permanently
    unfinished.
    """
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    status.record([{"scenario": "restaurant-tonight-madrid", "tier": 1,
                    "verdict": {"overall": 5, "scores": {}, "veredicto": "ok"},
                    "run": {"mechanism_report": {}}}], sandboxed=True)
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "| segment | scenarios | run | passing |" in board
    assert "completable" in board and "credentials" in board and "capability" in board
    assert "Coverage of the RUNNABLE list —" in board
    assert "never run)" in board
    assert "| tier | locale | run | of | passing |" in board
    # The case recorded here is a `credentials` one, so it must NOT count towards the runnable progress board.
    assert "Coverage of the RUNNABLE list — 0 of" in board


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


# ── scheduled triggers: the evidence a "remind me Wednesday" case lives or dies by ─────────────────────────
def test_only_the_triggers_THIS_conversation_created_count():
    """Jobs are durable and outlive a conversation, so an absolute count would credit a case with a reminder
    an earlier case in the same batch left behind. Reported by the fixing session as the reason V2-121's round
    could not be judged honestly: the report had no field for a reminder at all."""
    before = [{"id": "old", "name": "gimnasio", "schedule": "cada mes"}]
    after = before + [{"id": "new", "name": "seguro coche", "schedule": "2026-08-19 09:00",
                       "type": "once", "next_run": "2026-08-19T09:00", "prompt": "renovar"}]
    rep = verify.scheduled_report(before, after)
    assert [j["name"] for j in rep["created"]] == ["seguro coche"]
    assert rep["n_before"] == 1 and rep["n_after"] == 2 and rep["readable"] is True


def test_an_unreadable_scheduler_proves_nothing_either_way():
    """Fail-open in BOTH directions: never invent evidence of a reminder, never fail a case for a scheduler
    that couldn't be read. `readable` is what tells the judge which of the two it is looking at."""
    rep = verify.scheduled_report([], [])
    assert rep["created"] == [] and rep["readable"] is True     # readable and genuinely empty
    plain = verify.mechanism_report([{"cat": "flash"}], [])
    assert "scheduled_jobs" not in plain                        # absent when never sampled, not a false empty


def test_the_judge_is_told_that_an_unreadable_scheduler_is_not_a_failure():
    from tests.use_cases.e2e.agent import judge as J
    assert "scheduled_jobs.created" in J.RUBRIC
    assert "readable" in J.RUBRIC and "no prueba nada" in J.RUBRIC


# ── the continuous loop: two states per initiative, rotate on a failed re-test ─────────────────────────────
def _iso(monkeypatch, tmp_path):
    from tests.use_cases.e2e.agent import initiative as I
    monkeypatch.setattr(I, "INITIATIVES", tmp_path / "initiatives")
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    (tmp_path / "initiatives").mkdir(parents=True, exist_ok=True)
    (tmp_path / "modules" / "nucleo" / "tasks").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(I, "ENGINE", tmp_path)
    return I


def _res(overall=1, sid="unit-case"):
    return {"scenario": sid, "tier": 1,
            "run": {"transcript": [{"who": "tester", "text": "x"}], "mechanism_report": {}, "watchdog_log": []},
            "verdict": {"overall": overall, "scores": {}, "findings": [], "improvements": [],
                        "veredicto": "sigue sin funcionar"}}


def test_the_two_states_are_derived_from_the_TASKS_not_from_a_field(monkeypatch, tmp_path):
    """Both agents write to different files at unpredictable times. A status field inside the initiative that
    one of them forgets to flip would desynchronise the whole loop, so the tasks ARE the state."""
    I = _iso(monkeypatch, tmp_path)
    scn = _scn(id="unit-case", tier=1)
    assert I.initiative_state("unit-case") == ""              # never failed
    I.file_failure(_res(), scenario=scn, sandboxed=True)
    assert I.initiative_state("unit-case") == "awaiting_fix"  # state 1: the dev agent owes us a fix
    (I.MODULES / "nucleo" / "tasks" / "T900-uc-unit-case-verify.md").write_text(
        "---\nid: T900\nstatus: next\n---\n", encoding="utf-8")
    assert I.initiative_state("unit-case") == "awaiting_retest"   # state 2: we owe him a re-test
    assert I.awaiting_fix_count() == 0                        # answered work is NOT queue depth


def test_a_failed_retest_CLOSES_and_opens_a_successor(monkeypatch, tmp_path):
    """Operator's rule. A re-test that fails is not more evidence about the same error — the old one was
    addressed and what remains is a different one (V2-121 round 2: all three original blockers genuinely
    fixed, failed for a fourth reason one layer up). Piling that on the same file makes the dev agent read
    superseded diagnoses to find the live one."""
    I = _iso(monkeypatch, tmp_path)
    scn = _scn(id="unit-case", tier=1)
    first = I.file_failure(_res(), scenario=scn, sandboxed=True)["initiative"]
    out = I.rotate_failure(_res(), scenario=scn, sandboxed=True)
    assert out["initiative"] != first                        # a NEW workspace
    assert out["closed"] == first
    old = first.read_text(encoding="utf-8")
    assert "status: closed" in old and "CERRADA" in old
    assert out["initiative"].name in old                     # the closed one points forward
    # and the case now resolves to the successor, never back to the closed file
    assert I.find_initiative("unit-case") == out["initiative"]
    assert I.initiative_state("unit-case") == "awaiting_fix"
    assert I.awaiting_fix_count() == 1                       # counted once, not twice


def test_a_passing_retest_closes_the_workspace_without_marking_it_delivered(monkeypatch, tmp_path):
    """`delivered` is load-bearing: `test_roadmap_closure.py` forces a delivered initiative to be cited in
    engine/CLAUDE.md. A use-case round going green is not by itself a decision worth a line in the engine's
    context — that is the operator's call, not the harness's."""
    I = _iso(monkeypatch, tmp_path)
    scn = _scn(id="unit-case", tier=1)
    path = I.file_failure(_res(), scenario=scn, sandboxed=True)["initiative"]
    assert I.close_on_pass("unit-case", verdict="ya funciona", overall=5)["closed"] == path
    body = path.read_text(encoding="utf-8")
    assert "status: closed" in body and "delivered" not in body
    assert I.awaiting_fix_count() == 0
    assert I.find_initiative("unit-case") is None             # closed: out of the live board


def test_closing_fails_open_and_never_raises_into_a_batch(monkeypatch, tmp_path):
    I = _iso(monkeypatch, tmp_path)
    assert I.close_initiative(tmp_path / "nope.md", reason="x") is False
    assert I.close_on_pass("never-filed", verdict="", overall=5)["closed"] is None


# ── the real-data limit: what a case can HONESTLY be graded on ─────────────────────────────────────────────
def test_a_case_with_no_real_data_behind_it_is_graded_on_CONDUCT_not_outcome():
    """Operator, 2026-08-18: renewing a gym membership can never work with no gym, no account, no membership —
    "eso no es un fallo del use case". What is withdrawn from judgement is the OUTCOME; the CONDUCT stays,
    because the batch didn't fail for lacking a Netflix account, it failed for saying "ya tengo en marcha la
    cancelación". Without that half kept, this becomes an amnesty for hallucination."""
    from tests.use_cases.e2e.agent import derived as D
    note = D.data_note("renew-gym-membership")
    assert "el RESULTADO no se juzga" in note
    assert "FALLO MÁS GRAVE" in note and "afirmar que lo ha hecho" in note


def test_a_bookable_case_still_gets_its_SEARCH_half_graded_in_full():
    """The two classes differ in what's reachable. For a restaurant/ITV/hotel the search IS real and fully
    gradable — grading it as untestable would throw away the most valuable half and let "no encontré nada"
    pass as acceptable."""
    from tests.use_cases.e2e.agent import derived as D
    kind, missing = D.data_scope("itv-before-deadline")
    assert kind == "no_booking"
    note = D.data_note("itv-before-deadline")
    assert "se juzga ENTERA" in note
    assert "NO se penaliza no haber reservado" in note
    assert "sin haberlo buscado" in note        # but inventing the world is still the gravest failure


def test_the_limit_is_the_same_in_both_markets():
    """Every ES/US pair must be graded on the same bar: the operator's point is that the missing piece is
    identical in both markets ("ni en España ni en Estados Unidos"), not that one of them is luckier.

    Checked over the WHOLE catalog rather than one hand-picked pair — which is what a single example missed:
    `restaurant-tonight-madrid` carried the real-data limit and its twin `restaurant-tonight-nyc` did not, for
    months, because the twin's bare id is different and nobody had listed it. An example passes while the
    invariant is broken; a sweep cannot.
    """
    from tests.use_cases.e2e.agent import scenarios as SC
    from tests.use_cases.e2e.agent import segments as G
    scenarios = SC.all_scenarios()
    by_bare = {}
    for scn in scenarios:
        by_bare.setdefault(G.bare(scn.id), []).append(scn)
    for bare, group in by_bare.items():
        if len(group) < 2:
            continue
        limited = {("LÍMITE DE DATOS REALES" in s.success_checks
                    or "CAPACIDAD QUE NO EXISTE" in s.success_checks) for s in group}
        assert len(limited) == 1, f"{bare}: las variantes de mercado no llevan el mismo límite"

    # And the pairs that are twins by MEANING but not by id — the exact hole the sweep above cannot see,
    # because their bare ids differ. Listed explicitly so adding a third market forces a decision here.
    for a, b in (("restaurant-tonight-madrid", "restaurant-tonight-nyc"),
                 ("itv-before-deadline", "smog-check-before-deadline"),
                 ("coordinate-lunch-with-pedro", "coordinate-dinner-with-alex"),
                 ("confirm-restaurant-reservation-together", "confirm-restaurant-together"),
                 ("reschedule-meetup-conflict", "resolve-meetup-conflict"),
                 ("split-airbnb-with-marta", "split-airbnb-with-jordan"),
                 ("coordinate-lunch-whatsapp", "coordinate-dinner-whatsapp")):
        assert G.group_of(a) == G.group_of(b), f"{a} y {b} son el mismo caso en otro mercado"


def test_a_case_that_needs_nothing_real_carries_no_limit():
    """The counterweight: a plain fact lookup or a widget build is fully completable, so tagging it would
    excuse a real failure. `quick-fact` and the widget case must stay held to the full bar."""
    from tests.use_cases.e2e.agent import derived as D
    from tests.use_cases.e2e.agent import scenarios as SC
    assert D.data_scope("quick-fact-opening-hours") == ("", "")
    for sid in ("quick-fact-opening-hours", "build-workout-tracker-widget", "remember-and-remind-deadline"):
        scn = next(s for s in SC.all_scenarios() if s.id == sid)
        assert "LÍMITE DE DATOS REALES" not in scn.success_checks


def test_applying_the_limit_twice_does_not_duplicate_it():
    from tests.use_cases.e2e.agent import derived as D
    from tests.use_cases.e2e.agent import scenarios as SC
    scn = next(s for s in SC.all_scenarios() if s.id == "restaurant-tonight-madrid")
    once = scn.success_checks
    assert D.apply_data_note(scn).success_checks == once


def test_the_board_says_what_a_data_limited_case_was_graded_on(tmp_path, monkeypatch):
    """A `PASS` on a bookable case means "found real options and stopped at the wall", not "made a
    reservation". Without saying so on the board, the scoreboard would quietly overclaim what the product
    does — which is the one thing a scoreboard must never do."""
    monkeypatch.setattr(status, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(status, "BOARD_PATH", tmp_path / "STATUS.md")
    status.record([{"scenario": "renew-gym-membership__es", "tier": 1,
                    "verdict": {"overall": 5, "scores": {}, "veredicto": "dice qué le falta"},
                    "run": {"mechanism_report": {}}},
                   {"scenario": "quick-fact-opening-hours", "tier": 1,
                    "verdict": {"overall": 2, "scores": {}, "veredicto": "media pregunta"},
                    "run": {"mechanism_report": {}}}], sandboxed=True)
    led = status.load()["scenarios"]
    assert led["renew-gym-membership__es"]["data_limit"]["kind"] == "no_account"
    assert "data_limit" not in led["quick-fact-opening-hours"]   # fully completable: full bar
    board = (tmp_path / "STATUS.md").read_text(encoding="utf-8")
    assert "no real data behind them" in board and "no_account" in board
