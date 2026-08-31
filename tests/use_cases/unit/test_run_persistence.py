"""An interrupted batch must NOT discard verdicts that have already been earned.

Measured on 2026-08-20: a six-case verify batch was cut off after ~12 minutes, with
`cancel-subscription-before-charge__es` already run AND JUDGED—and the board was still showing the previous
run, because the only `record()` was AFTER the loop and was never reached. Everything the batch had
earned was lost, including the verdict that finally showed the CORRECT behavior (admitting that it cannot
access the operator's account instead of pretending to do so).

In an unattended loop, batches last tens of minutes and an interruption is not unusual: it may be a laptop
going to sleep, a killed tick, or a crash. And the cost is not just time—it is real, already-paid LLM spend.
"""
from __future__ import annotations

import inspect
import re

from tests.use_cases.e2e.agent import run as R, status as statusmod


def test_the_ledger_is_written_INSIDE_the_scenario_loop():
    """The structural assertion: `record()` must be inside the loop that iterates over the scenarios,
    not after it. This is checked by INDENTATION because that is what distinguishes the two positions—the
    function name is the same in both."""
    src = inspect.getsource(R.walk) if hasattr(R, "walk") else inspect.getsource(R)
    calls = [ln for ln in src.split("\n") if "statusmod.record(" in ln]
    assert calls, "nadie escribe el marcador"
    inside = [ln for ln in calls if len(ln) - len(ln.lstrip()) >= 8]
    assert inside, ("el único `record()` está al nivel de la función, o sea DESPUÉS del bucle: una tanda "
                    "interrumpida perdería todos sus veredictos")


def test_and_it_records_ONE_scenario_at_a_time():
    """`record()` only touches the scenarios it receives ("a batch of one cannot look as though it invalidated
    the other four," its own docstring says), so the call inside the loop must pass ONLY the latest result.
    Passing it the entire `results` would rewrite every scenario's `last_run` on each iteration."""
    src = inspect.getsource(R)
    inside = [ln.strip() for ln in src.split("\n")
              if "statusmod.record(" in ln and (len(ln) - len(ln.lstrip())) >= 8]
    assert inside
    assert any(re.search(r"record\(results\[-1:\]", ln) for ln in inside), inside


def test_no_batch_wide_record_rewrites_last_run_afterwards():
    """`last_run` is a field used to decide which verdicts are from BEFORE an environment change (it was
    used to remove the six measured with the English engine). A `record(results)` at the end would give every
    row the batch's END time, which is not when each case ran."""
    src = inspect.getsource(R)
    top_level = [ln for ln in src.split("\n")
                 if "statusmod.record(" in ln and 0 < (len(ln) - len(ln.lstrip())) < 8]
    assert not top_level, f"queda un record() de tanda completa que pisaría los last_run: {top_level}"


def test_record_of_one_leaves_the_other_rows_untouched(tmp_path, monkeypatch):
    """The behavior on which all of the above relies, asserted for real rather than read from a docstring."""
    monkeypatch.setattr(statusmod, "BOARD_PATH", tmp_path / "STATUS.md")
    monkeypatch.setattr(statusmod, "LEDGER_PATH", tmp_path / "status.json")

    def _res(sid, overall):
        return {"scenario": sid, "tier": 2, "run": {"transcript": [], "mechanism_report": {}},
                "verdict": {"overall": overall, "scores": {}, "veredicto": f"v-{sid}"}}

    statusmod.record([_res("caso-a", 5)], sandboxed=True)
    statusmod.record([_res("caso-b", 1)], sandboxed=True)
    led = statusmod.load()["scenarios"]
    assert set(led) == {"caso-a", "caso-b"}, "una tanda de uno no puede borrar la fila de la otra"
    assert led["caso-a"]["state"] == "PASS" and led["caso-b"]["state"] == "FAIL"


# ── a batch that measured NOTHING cannot pass as a retest ─────────────────────────────────────────────────
def test_a_batch_that_measured_nothing_is_reported_and_files_NOTHING(monkeypatch):
    """The failure that revealed this: an ORPHANED SANDBOX (`python -m server`, PPID 1) left behind by a
    killed batch kept the sandbox port, so every subsequent `run.py --verify` died at startup in less than a
    second. `_runner_alive()` does not see it—it looks for an `…agent.run` process, not the engine started by
    the batch—so the tick kept launching impossible batches and then READ THE PREVIOUS VERDICT from the board
    and acted on it: it logged "re-tested" for a case nobody ran and, worse, `rotate_failure` would have
    archived an initiative describing a run from an hour ago as if it were new evidence.

    STALE evidence is worse than none: the agent making the fix cannot distinguish it.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import status as statusmod, tick as T

    filed: list[str] = []
    logged: list[str] = []
    ledger = {"scenarios": {"cheapest-monitor": {"state": "FAIL", "overall": 1, "last_run": "2026-08-20 01:21",
                                                 "verdict": "veredicto VIEJO"}}}
    monkeypatch.setattr(T, "_log", lambda m: logged.append(m))
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": "cheapest-monitor", "slug": "cheapest-monitor",
                                      "task": Path("T999-uc-cheapest-monitor-verify.md")}])
    monkeypatch.setattr(T.I, "find_initiative", lambda sid: None)
    monkeypatch.setattr(T.I, "rotate_failure", lambda r, **kw: filed.append("ROTATE") or {})
    monkeypatch.setattr(T.I, "file_failure", lambda r, **kw: filed.append("FILE") or {})
    monkeypatch.setattr(T.I, "close_on_pass", lambda *a, **kw: filed.append("CLOSE"))
    monkeypatch.setattr(T.I, "note_inconclusive", lambda *a, **kw: filed.append("INCONCLUSIVE"))
    monkeypatch.setattr(statusmod, "load", lambda: ledger)          # the board does NOT change: nothing was measured
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")
    monkeypatch.setattr(T, "_run", lambda args, timeout_s: (1, "murió al arrancar el sandbox"))

    out = T._retest_pending()
    assert out["unrun"] == ["cheapest-monitor"]
    assert filed == [], f"actuó sobre un veredicto rancio: {filed}"
    said = " ".join(logged)
    assert "NO SE MIDIERON" in said
    # Both sandbox ports, read from the table (V2-459): the orphan keeps the one for the language of the
    # batch that left it behind, and the one reading the log does not know which it was. It used to say
    # «43918» raw, a number nobody has used since V2-459—a clue that sends you to look where there is nothing
    # is worse than no clue.
    from tests.platform import ports as PORTS
    for _p in (PORTS.SANDBOX_ES, PORTS.SANDBOX_US):
        assert str(_p) in said, "el log tiene que decir DÓNDE mirar, o el siguiente lo diagnostica de cero"


def test_but_a_batch_that_DID_measure_is_acted_on_normally(monkeypatch):
    """The sensitivity half: without this, "do not act on stale data" and "never act" would both pass, and the
    loop would stop closing initiatives and opening successors—in other words, stop functioning.

    The case must be EXECUTABLE and NOT grouped, or a different branch wins: the first version of this test
    used `cheapest-monitor`, which had just entered `GROUPED`, so the grouped branch correctly executed
    `continue` and the test interpreted that success as the failure it was looking for.
    """
    from pathlib import Path

    from tests.use_cases.e2e.agent import initiative as I2, scenarios as SC2, segments as SG2
    from tests.use_cases.e2e.agent import status as statusmod, tick as T

    sid = next(s.id for s in SC2.all_scenarios()
               if SG2.is_completable(s.id) and I2.GROUPED.get(SG2.bare(s.id)) is None)

    filed: list[str] = []
    ledger = {"scenarios": {sid: {"state": "FAIL", "overall": 1, "last_run": "2026-08-20 01:21"}}}
    monkeypatch.setattr(T, "_log", lambda m: None)
    monkeypatch.setattr(T.I, "scenarios_awaiting_verification",
                        lambda reg: [{"scenario": sid, "slug": sid,
                                      "task": Path(f"T999-uc-{sid}-verify.md")}])
    monkeypatch.setattr(T.I, "find_initiative", lambda s_: None)
    monkeypatch.setattr(T.I, "rotate_failure", lambda r, **kw: filed.append("ROTATE") or {})
    monkeypatch.setattr(statusmod, "summary_line", lambda: "x")

    def _run(args, timeout_s):
        # the batch DOES measure: it moves `last_run`, as `record()` does per scenario
        ledger["scenarios"][sid]["last_run"] = "2026-08-20 02:10"
        return (1, "")

    monkeypatch.setattr(T, "_run", _run)
    monkeypatch.setattr(statusmod, "load", lambda: ledger)

    out = T._retest_pending()
    assert out["unrun"] == []
    assert filed == ["ROTATE"], "una medición NUEVA sí tiene que mover la iniciativa"
