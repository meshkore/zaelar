"""The continuous loop must only launch cases that can REACH their own goal.

Written after the loop was re-armed for a 12-hour unattended run (2026-08-20). Step 2 of the tick tops the
queue up from the catalogue, and until this guard existed it pulled from all 125 cases — including the 78 that
cannot finish here (54 need a credential, a payment or a real object only the operator can supply; 24 need a
capability that is not built). Each one costs the same 3-6 minutes and a judge call as a real case and ends the
same way every time, so an unattended night would have filed initiative after initiative that the fixing agent
has no way to act on, while the runnable cases sat untouched.

The failure mode this guards is the expensive kind: nothing goes red, the board just fills with
work nobody can do. So the assertion is on the QUEUE the tick would actually launch, not on the filter helper.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import scenarios as SC, segments as SG, tick as T


def test_the_queue_only_ever_holds_runnable_cases(live_board):
    for s in T._unrun_scenarios():
        assert SG.is_completable(s.id), (
            f"«{s.id}» está en la cola del tick pero su segmento es «{SG.group_of(s.id)}»: "
            f"gastaría una tanda entera para acabar pidiendo algo que no tenemos")


def test_and_the_blocked_ones_are_genuinely_excluded():
    """The other half: without this, “filters” and “the queue is empty” pass the same test."""
    queued = {s.id for s in T._unrun_scenarios()}
    blocked = [s.id for s in SC.all_scenarios() if not SG.is_completable(s.id)]
    assert blocked, "la tabla de segmentos dice que no hay ningún caso bloqueado — eso ya sería el bug"
    assert not (queued & set(blocked))


def test_the_queue_is_not_empty_while_runnable_cases_remain_untried(live_board):
    """And the filter must not get too clever: while an executable case remains without a verdict, the queue has it.

    If one day all 47 have passed, this switches off by itself—the catalogue will genuinely be exhausted, which is the
    condition that `_top_up` already knows how to report.
    """
    from tests.use_cases.e2e.agent import status as statusmod

    led = statusmod.load().get("scenarios") or {}
    judged = {k for k, e in led.items() if (e or {}).get("state") in ("PASS", "FAIL")}
    untried = [s.id for s in SC.all_scenarios() if SG.is_completable(s.id) and s.id not in judged]
    assert len({s.id for s in T._unrun_scenarios()}) == len(untried)


def test_es_and_us_are_never_mixed_in_one_batch():
    """The language is a PROCESS setting (`ZAELAR_LANGUAGE`), so a mixed batch would score ES cases against answers
    in English—the artifact that nearly produced false bug reports on 2026-08-18. The queue is ordered with ES
    first precisely so that the `MAX_PER_TICK` cutoff always falls within a single locale."""
    q = T._unrun_scenarios()
    if not q:
        return
    lang = q[0].locale
    picked = [s for s in q if s.locale == lang][:T.MAX_PER_TICK]
    assert len({s.locale for s in picked}) == 1


def test_a_case_that_only_ever_died_in_INFRA_stays_in_the_queue(live_board):
    """An `INFRA` is not a verdict: the harness died before judging, so that case has NOT been measured.

    Counting it as tested silently removed `build-workout-tracker-widget`—the only executable case covering widget
    generation—because it died with a 403 from the broker, and every tick skipped it thereafter as already attempted.
    A case disappearing from the queue without anything turning red is the kind of failure noticed only weeks later,
    when someone asks why coverage is not increasing.
    """
    from tests.use_cases.e2e.agent import status as statusmod

    led = statusmod.load().get("scenarios") or {}
    infra = [k for k, e in led.items() if (e or {}).get("state") == "INFRA" and SG.is_completable(k)]
    queued = {s.id for s in T._unrun_scenarios()}
    for sid in infra:
        assert sid in queued, f"«{sid}» solo tiene un INFRA (nunca se midió) y la cola lo está saltando"


def test_but_a_real_verdict_does_retire_a_case(live_board):
    """The other half: PASS and FAIL are measurements, and re-running them is what the verify path does."""
    from tests.use_cases.e2e.agent import status as statusmod

    led = statusmod.load().get("scenarios") or {}
    judged = [k for k, e in led.items() if (e or {}).get("state") in ("PASS", "FAIL")]
    assert judged, "el marcador no tiene ni un veredicto — este test no estaría probando nada"
    queued = {s.id for s in T._unrun_scenarios()}
    assert not (queued & set(judged))


def test_a_verify_task_that_points_at_NO_case_is_reported_not_swallowed(monkeypatch):
    """`scenarios_awaiting_verification` promises in its docstring that an unresolvable slug “is REPORTED, never
    skipped silently.” Until 2026-08-20 that promise broke right here: `_retest_pending` filtered with
    `if p["scenario"]`, and two tasks (`progreso-fabricado`, `progreso-fabricado-idioma`)—which requested a retest of a
    PATTERN, not a case—remained at `status: next` from 2026-08-18, waiting for an impossible run.

    The cost is not an error: it is that the fixing agent waits for a retest that will never run, and
    “waiting for retest: 4” reports a number that was mostly fiction. The tick cannot ACT on them, but it can name them.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod

    logged: list[str] = []
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": None, "slug": "progreso-fabricado",
                                      "task": Path("T326-uc-progreso-fabricado-verify.md")}])
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})

    out = T._retest_pending()
    assert out["retested"] == 0
    assert out.get("orphan") == ["T326-uc-progreso-fabricado-verify.md"]
    said = " ".join(logged)
    assert "T326-uc-progreso-fabricado-verify.md" in said, "tiene que NOMBRAR la tarea que nadie va a correr"
    assert "progreso-fabricado" in said


def test_but_a_resolvable_task_is_not_reported_as_an_orphan(monkeypatch):
    """The sensitivity half: without this, “report orphans” and “report everything” pass equally, and the tick log
    would fill with warnings about tasks that are actually being run."""
    from tests.use_cases.e2e.agent import status as statusmod

    logged: list[str] = []
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": "cheapest-monitor", "slug": "cheapest-monitor",
                                      "task": __import__("pathlib").Path("T999-uc-cheapest-monitor-verify.md")}])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, ""))
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    out = T._retest_pending()
    assert out.get("orphan") == []
    assert "no apuntan a ningún caso" not in " ".join(logged)


def test_two_verify_tasks_for_the_SAME_case_are_measured_once(monkeypatch):
    """On 2026-08-20 the fixing agent responded with `find-theatre-tickets__es` in TWO separate tasks
    (T434 and T438), and the tick announced the case twice and processed its accounting twice for ONE verdict:
    the same round written twice in the umbrella and an inflated `retested` count. It is not a second run cost—
    `run.py --verify` measures once and closes both tasks—it is the ledger duplicating the entry.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod

    logged: list[str] = []
    seen_cases: list[str] = []
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification", lambda reg: [
        {"scenario": "find-theatre-tickets__es", "slug": "find-theatre-tickets-es",
         "task": Path("T434-uc-find-theatre-tickets-es-verify.md")},
        {"scenario": "find-theatre-tickets__es", "slug": "find-theatre-tickets-es",
         "task": Path("T438-uc-find-theatre-tickets-es-verify.md")},
    ])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: (seen_cases.append(sid), None)[1])
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, ""))
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    out = T._retest_pending()
    assert out["retested"] == 1, "un caso medido una vez se cuenta una vez, haya 1 o 5 tareas pidiéndolo"
    assert seen_cases == ["find-theatre-tickets__es"], "la contabilidad del caso corrió dos veces"
    said = " ".join(logged)
    assert "T438-uc-find-theatre-tickets-es-verify.md" in said, (
        "colapsar en silencio deja al operador sin saber por qué una tarea `next` no aparece en el log")


def test_but_distinct_cases_are_all_kept(monkeypatch):
    """The sensitivity half: deduplicating by CASE must not turn into “only the first one is retested.”"""
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod

    monkeypatch.setattr(T, "_log", lambda m: None)
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification", lambda reg: [
        {"scenario": "cheapest-monitor", "slug": "cheapest-monitor", "task": Path("T1-verify.md")},
        {"scenario": "remember-and-remind-deadline", "slug": "remember-and-remind-deadline",
         "task": Path("T2-verify.md")},
    ])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, ""))
    monkeypatch.setattr(statusmod, "load", lambda: {"scenarios": {}})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    assert T._retest_pending()["retested"] == 2


def test_run_verify_drives_one_case_ONCE_and_closes_BOTH_of_its_tasks():
    """The other half of deduplication, in `run.py`. The tick collapsed its ACCOUNTING, but the component driving the
    conversation is the runner, and there the duplicated case was actually run twice.

    Measured on 2026-08-20 10:00: T434 and T438 both requested `find-theatre-tickets__es`, and umbrella V2-167
    ended with identical rounds 13 and 15—same measurement, ~4 minutes of the shift wasted, and the initiative
    evidence counting twice as many attempts as actually occurred. And because the map was `{case: task}`, only ONE
    of the two tasks was closed: the other remained in `next`, requesting a retest that had already happened.

    This asserts the BEHAVIOR of `_verify_batch`, rather than reading the source: a test that searches for text in the
    code has already failed once in this suite by finding what it was looking for... inside the comment explaining
    why it should not be done.
    """
    from pathlib import Path
    from types import SimpleNamespace

    from tests.use_cases.e2e.agent import run as R

    registry = {"find-theatre": SimpleNamespace(id="find-theatre"), "otro": SimpleNamespace(id="otro")}
    pend = [{"scenario": "find-theatre", "task": Path("T434-verify.md")},
            {"scenario": "find-theatre", "task": Path("T438-verify.md")},
            {"scenario": "otro", "task": Path("T440-verify.md")},
            {"scenario": None, "task": Path("T999-huerfana.md")}]

    chosen, tasks = R._verify_batch(pend, registry)
    assert [c.id for c in chosen] == ["find-theatre", "otro"], (
        "el caso se conduciría dos veces: media conversación y media ronda de más")
    assert [t.name for t in tasks["find-theatre"]] == ["T434-verify.md", "T438-verify.md"], (
        "las DOS tareas tienen que cerrarse; quedarse una en `next` pide un re-test que ya se hizo")


def test_and_a_task_naming_an_unknown_case_never_reaches_the_batch():
    """The sensitivity half: collapsing by case must not let a key absent from the catalogue slip through—
    `registry[sid]` would blow up the entire batch because of a misnamed task."""
    from pathlib import Path

    from tests.use_cases.e2e.agent import run as R

    chosen, tasks = R._verify_batch([{"scenario": "no-existe", "task": Path("T1.md")}], {})
    assert chosen == [] and tasks == {}


def test_a_verify_task_named_with_the_RAW_scenario_id_still_resolves(monkeypatch):
    """The fixing agent writes these names by hand, and on 2026-08-20 FOUR of its eight retest requests
    were invisible: two used the raw ID (`book-hotel-night-known__es`, where the convention collapses `__` to `-`)
    and two used a partial slug. Rejecting them is technically correct and practically useless—the other agent waits
    for a retest that never runs, while this side reports an orphan that is actually just a spelling difference.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import initiative as I

    monkeypatch.setattr(I, "pending_verifications", lambda: [
        {"slug": "book-hotel-night-known__es", "task": Path("T447-verify.md")},
        {"slug": "cheapest-monitor", "task": Path("T446-verify.md")},
    ])
    got = {p["task"].name: p["scenario"] for p in I.scenarios_awaiting_verification(
        {"book-hotel-night-known__es": object(), "cheapest-monitor": object()})}
    assert got["T447-verify.md"] == "book-hotel-night-known__es"
    assert got["T446-verify.md"] == "cheapest-monitor"


def test_but_an_AMBIGUOUS_slug_is_refused_and_says_between_which(monkeypatch):
    """The half that matters: `find-theatre-tickets` matches __es and __us. Choosing one gives a verdict that looks
    good but proves nothing—the fix would have been verified against the other language—so neither is chosen. But
    it must SAY which two it is uncertain between, as that is the only thing that allows renaming the task and moving on.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import initiative as I

    monkeypatch.setattr(I, "pending_verifications", lambda: [
        {"slug": "find-theatre-tickets", "task": Path("T441-verify.md")}])
    p = I.scenarios_awaiting_verification(
        {"find-theatre-tickets__es": object(), "find-theatre-tickets__us": object()})[0]
    assert p["scenario"] is None
    assert "find-theatre-tickets__es" in p["why"] and "find-theatre-tickets__us" in p["why"]
