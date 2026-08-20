"""Which judge graded a case is part of the result, not a detail of the run.

Measured on 2026-08-20: one day's reports show the SAME case graded by four different judges — glm-4.6,
two aliases of deepseek-v4-flash, and older runs with nothing sealed — because the judge chain falls back
when the vendor is rate-limited. Over that day's gradings the two live judges differ by 0.44 of a point on
average. Without this field, a case that changed ruler between two rounds reads on the board exactly like
a case that regressed.
"""
from tests.use_cases.e2e.agent import status


def _row(judge):
    res = [{"scenario": "x", "verdict": {"overall": 3, "scores": {"mecanismo": 3}, "_judge_model": judge},
            "run": {"mechanism_report": {}}}]
    return status.record(res, sandboxed=True)["scenarios"]["x"]


def test_the_judge_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "PATH", tmp_path / "status.json", raising=False)
    monkeypatch.setattr(status, "MD", tmp_path / "STATUS.md", raising=False)
    assert _row("glm-4.6")["judge"] == "glm-4.6"


def test_the_broker_alias_is_folded_onto_the_model(tmp_path, monkeypatch):
    """`deepseek/deepseek-v4-flash` and `deepseek-v4-flash` are the same ruler down two different roads."""
    monkeypatch.setattr(status, "PATH", tmp_path / "status.json", raising=False)
    monkeypatch.setattr(status, "MD", tmp_path / "STATUS.md", raising=False)
    assert _row("deepseek/deepseek-v4-flash")["judge"] == "deepseek-v4-flash"


def test_an_unsealed_judge_is_empty_not_invented(tmp_path, monkeypatch):
    monkeypatch.setattr(status, "PATH", tmp_path / "status.json", raising=False)
    monkeypatch.setattr(status, "MD", tmp_path / "STATUS.md", raising=False)
    assert _row(None)["judge"] == ""
