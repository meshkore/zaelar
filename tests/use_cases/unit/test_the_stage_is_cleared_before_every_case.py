"""The stage is cleared BEFORE EVERY case — also before the first one.

Until 2026-08-21, the reset between cases lived after an `if results:`, meaning it only ran starting with the
SECOND one. In a single-case batch it never ran, and on the stage —which is deliberately persistent: same
port, viewed live— that meant **the first case of each round inherited the canvas, tasks, and workers from the
PREVIOUS round**. The operator loaded the ES test and the first thing they saw was the previous run's dirty
screen.

The requested rule is exactly what `hard_reset()` does and does NOT do: it kills live work and clears the
canvas, while LEAVING memory and state IN PLACE (`/reset/hard`, not `/api/reset/full` with `wipe_memory`). Both
sides are checked here, because “cleaning more” is the easy regression: clearing memory would require killing
the process and, in addition, discovery cases seed preferences that must survive the reset.
"""
from __future__ import annotations

import inspect

from tests.use_cases.e2e.agent import (config, probe_client, report as reportmod, run as R,
                                       scenarios as SC, status as statusmod)


def _s(sid: str):
    return SC.UseCaseScenario(id=sid, locale="es", tier=2, persona_brief="p", opening_line="o",
                              success_checks="s")


def _batch(monkeypatch, tmp_path, ids: list[str]) -> list[str]:
    """Runs `_run_batch` for real with the outside world disarmed, and returns the ORDER of what happened.

    It calls the REAL function instead of checking the source: a `grep` guard would remain green on the day
    someone puts the reset behind a condition again, which is exactly the failure this closes.
    """
    order: list[str] = []
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(probe_client, "hard_reset", lambda: order.append("reset") or {})
    monkeypatch.setattr(R.time, "sleep", lambda *_a, **_k: None)
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **k: (
        order.append(f"run:{scn.id}") or {"scenario": scn.id, "tier": scn.tier, "channel": "probe",
                                          "run": {}, "verdict": {"overall": 5}}))
    # The marker and report are LIVE operator artifacts: a unit test does not touch them (conftest already
    # isolates its own artifacts; this closes off the two that remain outside it).
    monkeypatch.setattr(statusmod, "record", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "attach_workspaces", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "")
    monkeypatch.setattr(reportmod, "build", lambda *a, **k: tmp_path / "r.md")
    # THE TREE STAMP, PINNED. `_run_batch` rereads it between cases from V2-282 (a batch lasts hours and the
    # startup guards do not see what happens during it), so without pinning it these tests ask for the git
    # state of the machine running them: green with a clean tree, red with an edit in progress. It is the
    # “a test made green by the ENVIRONMENT” that the root conftest already guards against by language and
    # config.
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "fijo", "dirty": [], "n_dirty": 0})
    R._run_batch([_s(i) for i in ids], sandboxed=True, args_no_file=True)
    return order


def test_the_first_case_of_a_batch_also_starts_clean(monkeypatch, tmp_path):
    assert _batch(monkeypatch, tmp_path, ["uno"]) == ["reset", "run:uno"]


def test_every_case_gets_its_own_reset_and_it_comes_first(monkeypatch, tmp_path):
    assert _batch(monkeypatch, tmp_path, ["a", "b", "c"]) == [
        "reset", "run:a", "reset", "run:b", "reset", "run:c"]


def test_a_failed_reset_does_not_lose_the_batch(monkeypatch, tmp_path):
    """The reset is best-effort: an engine that does not respond to the reset leaves the case dirty, not the batch dead."""
    def boom():
        raise RuntimeError("motor mudo")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(probe_client, "hard_reset", boom)
    monkeypatch.setattr(R.time, "sleep", lambda *_a, **_k: None)
    ran: list[str] = []
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **k: (
        ran.append(scn.id) or {"scenario": scn.id, "tier": scn.tier, "channel": "probe",
                               "run": {}, "verdict": {"overall": 5}}))
    monkeypatch.setattr(statusmod, "record", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "attach_workspaces", lambda *a, **k: None)
    monkeypatch.setattr(statusmod, "summary_line", lambda: "")
    monkeypatch.setattr(reportmod, "build", lambda *a, **k: tmp_path / "r.md")
    monkeypatch.setattr(config, "code_stamp", lambda: {"sha": "fijo", "dirty": [], "n_dirty": 0})
    R._run_batch([_s("a"), _s("b")], sandboxed=True, args_no_file=True)
    assert ran == ["a", "b"]


def test_the_reset_that_runs_is_the_one_that_keeps_memory():
    """COUNTERWEIGHT, and this is the side through which it breaks when “improved.”

    `hard_reset()` calls `/reset/hard`. `/api/reset/full` with `wipe_memory` is ANOTHER endpoint: it requires
    killing the process (SQLite is in use) and would wipe out the preferences that discovery cases seed BEFORE
    speaking — the case would measure the memory distiller and report it as the agent failing to reason. If
    someone changes the endpoint “to clean everything,” this turns red.
    """
    body = inspect.getsource(probe_client.hard_reset)
    call = [ln.strip() for ln in body.splitlines() if "_post(" in ln]
    assert call == ['return _post("/reset/hard", {}, timeout=60.0)'], call
