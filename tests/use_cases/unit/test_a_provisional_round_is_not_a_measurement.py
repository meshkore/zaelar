"""A round measured on a moving tree still writes a row — and the row must say so.

On 2026-08-20 a round ran with `--allow-dirty` while another agent was editing
`widgets/navegador/act_api.py`; the case had spawned a web worker, so the confound touched exactly what was
being measured. The harness banked the score into the board in the same minute its operator was telling the
cluster he was discarding it. The rule existed only in prose, so it was not a rule.
"""
from __future__ import annotations

import types

from tests.use_cases.e2e.agent import run as R
from tests.use_cases.e2e.agent import status as S


def _args(**kw):
    return types.SimpleNamespace(**{"allow_dirty": False, **kw})


def test_a_clean_round_is_not_flagged():
    assert R._provisional(_args()) == ""


def test_a_dirty_round_says_why_it_does_not_count():
    why = R._provisional(_args(allow_dirty=True))
    assert why and "allow-dirty" in why


def test_the_flag_reaches_the_row(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    res = {"scenario": "x", "tier": 1, "verdict": {"overall": 3, "scores": {}, "veredicto": "v"},
           "run": {"transcript": [], "mechanism_report": {}}}
    led = S.record([res], sandboxed=True, provisional="porque si")
    assert led["scenarios"]["x"]["provisional"] == "porque si"


def test_and_a_clean_row_carries_no_flag(tmp_path, monkeypatch):
    """Sensitivity: if `provisional` were always truthy the first test would pass and mean nothing."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    res = {"scenario": "y", "tier": 1, "verdict": {"overall": 5, "scores": {}, "veredicto": "v"},
           "run": {"transcript": [], "mechanism_report": {}}}
    led = S.record([res], sandboxed=True)
    assert led["scenarios"]["y"]["provisional"] is None


def test_the_batch_PASSES_the_flag_down(monkeypatch):
    """The classic failure of this repo, and it bit while writing this very feature: the first draft called
    `_provisional(args)` INSIDE `_run_batch`, where `args` does not exist. The NameError landed in the loop's
    `except Exception` — the one that keeps one scenario's hiccup from losing the batch — so every scenario
    would have crashed in silence and the report would have come back empty, not broken."""
    seen: list[dict] = []
    monkeypatch.setattr(R, "_run_scenario", lambda scn, **kw: seen.append(kw) or {
        "scenario": scn.id, "tier": 1, "channel": "probe", "run": {}, "verdict": {"overall": 3},
        "drive_model": "m"})
    monkeypatch.setattr(R.statusmod, "record", lambda *a, **k: None)
    monkeypatch.setattr(R.reportmod, "build", lambda *a, **k: R.config.RUNS_DIR / "x.md")
    monkeypatch.setattr(R.initiativemod, "file_failure", lambda *a, **k: None)

    class _S:
        id, tier, channel, locale = "s", 1, "probe", "es"
        goal = persona_brief = opening_line = ""
        success_checks = expected_signals = forbidden_signals = ()
        turns = 2

    R._run_batch([_S()], sandboxed=True, args_no_file=True, provisional="por esto")
    assert seen, "the batch swallowed an exception instead of running the scenario"
    assert seen[0].get("provisional") == "por esto"
