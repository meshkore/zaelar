"""A BLOCKED case does not open its own initiative — but its HONESTY failure is not lost.

Both sides of this were measured on 2026-08-20, and both come at a cost:

· **Opening an initiative per case** filled the work board with work that no one can do. `--verify` runs what the
  fixing agent requests (correctly, honoring its request), while the ROTATION path opened a new initiative without
  checking the segment: this opened V2-172/173 and, in the SAME batch, V2-174/175 — the same two cases
  filed twice, minutes after they were closed because they needed operator credentials.

· **Suppressing it entirely** —my first fix— would have thrown away the only finding that mattered. Those two cases
  scored `naturalidad 5` with `mecanismo 1-2`: unable to do the work, the agent REPORTED it as completed
  («it imagined the user's session»). Seeing that requires no credentials — it is the transcript compared with the
  mechanism report from the same run — and it is a real, actionable defect.

So the round goes to the shared umbrella, and no per-case task is created.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from tests.use_cases.e2e.agent import initiative as I, scenarios as SC, segments as SG

BLOCKED = "cancel-subscription-before-charge__es"
RUNNABLE = "cheapest-monitor"


def _result(sid: str, overall: int = 2) -> dict:
    return {"scenario": sid, "tier": 5,
            "run": {"transcript": [], "turns_used": 8,
                    "mechanism_report": {"families_observed": ["flash"], "missing_signals": ["worker"]},
                    "watchdog_log": []},
            "verdict": {"overall": overall, "scores": {"naturalidad": 5, "mecanismo": 1},
                        "findings": [], "improvements": [], "veredicto": "narró un login que no ocurrió"}}


def test_the_blocked_case_is_confirmed_blocked_first():
    """The premise. If it is ever unblocked, this file will stop testing what it claims to test."""
    assert not SG.is_completable(BLOCKED)
    assert SG.is_completable(RUNNABLE)


def test_a_blocked_failure_never_creates_its_own_initiative_or_task(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    res = I.file_failure(_result(BLOCKED), scenario=SC.registry()[BLOCKED], sandboxed=True, force_new=True)
    assert res.get("task") is None
    assert res.get("blocked"), "tiene que decir QUE está bloqueado y qué falta"
    assert "necesita" in res["blocked"]
    # with the umbrella absent (empty tmp_path), no initiative is invented
    assert res.get("initiative") is None
    assert not list(tmp_path.glob("V2-*.md")), "no puede haber creado ningún fichero de iniciativa"


def test_but_its_honesty_failure_lands_in_the_shared_umbrella(tmp_path, monkeypatch):
    umb = tmp_path / I.BLOCKED_UMBRELLA
    umb.write_text("---\nid: V2-176\ntitle: \"x\"\ndate: 2026-08-20\nstatus: open\n---\n\n# paraguas\n",
                   encoding="utf-8")
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)

    res = I.file_failure(_result(BLOCKED), scenario=SC.registry()[BLOCKED], sandboxed=True, force_new=True)
    assert res["initiative"] == umb
    assert res["round"] == 1
    assert res.get("task") is None

    body = umb.read_text(encoding="utf-8")
    assert BLOCKED in body, "la ronda tiene que NOMBRAR el caso: el paraguas es de varios"
    assert "HONESTIDAD" in body, "tiene que decir QUÉ se está midiendo en un caso que no puede completar"
    assert "narró un login que no ocurrió" in body

    # a second run ADDS a round; it does not replace or fragment it
    I.file_failure(_result("renew-gym-membership__es"), scenario=SC.registry()["renew-gym-membership__es"],
                   sandboxed=True, force_new=True)
    assert len(re.findall(r"^## Ronda ", umb.read_text(encoding="utf-8"), re.M)) == 2
    assert not [p for p in tmp_path.glob("V2-*.md") if p != umb]


def test_a_RUNNABLE_case_still_gets_its_own_initiative(tmp_path, monkeypatch):
    """The sensitivity half, and the one that matters: without it, «do not file blocked cases» and «do not file anything»
    pass the same test, and the harness would be silent precisely for cases it can measure."""
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    (tmp_path / "modules" / "nucleo" / "tasks").mkdir(parents=True)
    res = I.file_failure(_result(RUNNABLE), scenario=SC.registry()[RUNNABLE], sandboxed=True, force_new=True)
    assert res.get("blocked") is None
    assert res.get("initiative") is not None and res["initiative"].is_file()
    assert res.get("task") is not None, "un caso ejecutable SÍ trae su tarea de arreglo"


def test_a_closed_umbrella_is_not_resurrected(tmp_path, monkeypatch):
    """Fail-open: if someone closes the umbrella, a blocked case does not reopen it or mint a per-case one — which is
    exactly the fragmentation this exists to prevent."""
    umb = tmp_path / I.BLOCKED_UMBRELLA
    umb.write_text("---\nid: V2-176\ntitle: \"x\"\ndate: 2026-08-20\nstatus: closed\n---\n", encoding="utf-8")
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    res = I.file_failure(_result(BLOCKED), scenario=SC.registry()[BLOCKED], sandboxed=True, force_new=True)
    assert res.get("initiative") is None
    assert res.get("blocked")


def test_the_real_umbrella_exists_and_is_open():
    """The name is written in the code, so a silent rename would leave it without a destination and blocked cases
    would go back to filing nothing without turning red."""
    path = I.INITIATIVES / I.BLOCKED_UMBRELLA
    if not path.is_file():
        pytest.skip("el paraguas no está en disco (roadmap gitignoreado en un clone limpio)")
    assert I._blocked_umbrella() is not None, f"{I.BLOCKED_UMBRELLA} existe pero está cerrado"


def test_an_UNCLASSIFIED_case_still_files(tmp_path, monkeypatch):
    """`segment_of` returning None means «unclassified», which its own docstring calls «a bug, not a state».
    Treating it as blocked is the DANGEROUS interpretation: a new case would silently stop producing work orders,
    which is exactly the failure this guard prevents in the other direction. Eight harness tests using a synthetic
    scenario (`unit-mf`), not the catalog, exposed it — and with the first version of the guard they stopped filing."""
    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    monkeypatch.setattr(I, "MODULES", tmp_path / "modules")
    (tmp_path / "modules" / "nucleo" / "tasks").mkdir(parents=True)
    assert SG.segment_of("caso-que-no-existe") is None
    scn = SC.UseCaseScenario(id="caso-que-no-existe", locale="es", tier=2,
                             persona_brief="x", opening_line="y", success_checks="z")
    res = I.file_failure(_result("caso-que-no-existe"), scenario=scn, sandboxed=True)
    assert res.get("blocked") is None
    assert res.get("initiative") is not None and res["initiative"].is_file()
    assert res.get("task") is not None


def test_the_tick_does_not_file_a_blocked_case_a_SECOND_time(monkeypatch):
    """`run.py --verify` already files the round; the tick only NAMES it.

    Filing in both places wrote the SAME round twice —same case, same minute— as seen when reading
    V2-176 on 2026-08-20 (identical rounds 3 and 4). The GROUPED branch immediately above already handled this
    correctly for the same reason; the blocked branch did not. A duplicate does not turn red: it merely makes an
    initiative's evidence count twice as many attempts as actually occurred, which is worse than having none.

    This asserts the BEHAVIOR (was `file_failure` called?) rather than reading the source: the first version of
    this test searched for the name in the branch text and found it... in the comment explaining why it should
    NOT be called.
    """
    from tests.use_cases.e2e.agent import status as statusmod, tick as T

    calls: list[str] = []
    monkeypatch.setattr(T.I, "file_failure",
                        lambda result, **kw: calls.append(kw["scenario"].id) or {"initiative": None})
    monkeypatch.setattr(T.I, "rotate_failure",
                        lambda result, **kw: calls.append("ROTATE:" + kw["scenario"].id) or {})
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": BLOCKED, "task": "T999"}])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    # The marker has to MOVE with the batch: if `last_run` does not change, the tick rightly concludes that nothing
    # was measured and does not classify the case at all (see `test_run_persistence.py`). What is tested here is
    # the BLOCKED branch, so the batch does measure something.
    ledger = {"scenarios": {BLOCKED: {"state": "FAIL", "overall": 2, "last_run": "2026-08-20 01:00",
                                      "verdict": "narró un login que no ocurrió"}}}

    def _run(args, timeout_s):
        ledger["scenarios"][BLOCKED]["last_run"] = "2026-08-20 02:20"
        return (1, "salida de prueba")

    monkeypatch.setattr(T, "_run", _run)
    monkeypatch.setattr(statusmod, "load", lambda: ledger)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    out = T._retest_pending()
    assert out["retested"] == 1
    assert out["blocked"], "tiene que DECIR que lo re-probó y estaba bloqueado"
    assert calls == [], f"el tick volvió a archivar el caso bloqueado: {calls}"


def test_a_runnable_case_can_also_be_grouped_under_the_umbrella():
    """`cheapest-monitor` is RUNNABLE and still shares V2-176's defect — it was on its way to a third
    initiative of its own. Being in GROUPED is what prevents it from fragmenting again on its own."""
    assert SG.is_completable("cheapest-monitor")
    assert I.GROUPED.get("cheapest-monitor") == I.BLOCKED_UMBRELLA
    path = I.INITIATIVES / I.BLOCKED_UMBRELLA
    if path.is_file():
        assert I.grouped_for("cheapest-monitor") is not None


def test_a_case_that_is_BOTH_blocked_and_grouped_files_in_its_OWN_umbrella(monkeypatch, tmp_path):
    """`find-theatre-tickets__es` needs an account and card (blocked) **and** is in V2-167 (grouped). Its
    own umbrella takes precedence.

    Without this, the SAME measurement lands in one file or the other depending on which path files it —the blocked
    branch writes to V2-176, the grouped branch to V2-167— and a case's evidence is split between two initiatives.
    This was seen on 2026-08-20 while preparing the handoff: both umbrellas had rounds for the same case, and the
    person who has to fix it cannot tell that half is missing.
    """
    from tests.use_cases.e2e.agent import initiative as I, segments as SG, scenarios as SC

    sid = "find-theatre-tickets__es"
    assert not SG.is_completable(sid), "el caso de prueba tiene que estar BLOQUEADO"
    assert I.grouped_for(sid) is not None, "y AGRUPADO"

    monkeypatch.setattr(I, "INITIATIVES", tmp_path)
    own = tmp_path / I.GROUPED["find-theatre-tickets"]
    own.write_text("---\nstatus: open\n---\n\n# propio\n", encoding="utf-8")
    (tmp_path / I.BLOCKED_UMBRELLA).write_text("---\nstatus: open\n---\n\n# bloqueados\n", encoding="utf-8")

    res = I.file_failure(
        {"scenario": sid, "tier": 1,
         "run": {"transcript": [], "mechanism_report": {}, "watchdog_log": []},
         "verdict": {"overall": 2, "scores": {}, "veredicto": "narró lo que no pasó",
                     "findings": [], "improvements": []}},
        scenario=SC.registry()[sid], sandboxed=True)

    assert res["initiative"] == own, (
        f"la ronda fue a {res['initiative'].name if res['initiative'] else None} en vez de a su paraguas propio")
    assert "Ronda 1" in own.read_text(encoding="utf-8")
    assert res.get("blocked"), "sigue teniendo que DECIR que está bloqueado, solo cambia dónde escribe"
