"""The clean-clone check is one command, and it follows the tree (refactor2710-99).

What a self-hoster gets — a clone with none of this machine's state — is checked by
`python -m tests.infrastructure.clean_clone`: ruff, compileall of every engine package, the event freezers and
`tests/infrastructure`. These tests read its PLAN, never clone: the run itself is the deliberate step.
"""
from __future__ import annotations

import pathlib

from tests.infrastructure import clean_clone as cc

ENGINE = pathlib.Path(__file__).resolve().parents[3]


def test_the_plan_is_ruff_compileall_the_freezers_and_infrastructure():
    steps = cc.plan(ENGINE, "py")
    assert [name for name, _ in steps] == ["ruff", "compileall", "freezers", "infrastructure"]
    argv = dict(steps)
    assert argv["ruff"][1:] == ["-m", "ruff", "check", "."]
    assert argv["infrastructure"][1:] == ["tests/watchdog.py", "tests/infrastructure"], "a wide pass runs under the watchdog"


def test_every_engine_package_is_compiled_and_the_suite_is_not():
    pkgs = cc.packages(ENGINE)
    assert {"nucleo", "memory", "voice", "server", "widgets", "search", "rules"} <= set(pkgs)
    assert "tests" not in pkgs
    assert dict(cc.plan(ENGINE, "py"))["compileall"][4:] == pkgs


def test_the_freezers_are_found_not_listed(tmp_path):
    """A freezer born tomorrow is in the check without editing it."""
    found = cc.freezers(ENGINE)
    assert "tests/infrastructure/unit/test_a_pulse_or_energy_event_survives_a_move.py" in found
    assert all(pathlib.Path(f).name.startswith("test_") and "surviv" in f for f in found)
    (tmp_path / "tests" / "x").mkdir(parents=True)
    (tmp_path / "tests" / "x" / "test_a_new_event_survives_a_rename.py").write_text("")
    (tmp_path / "tests" / "x" / "test_something_else.py").write_text("")
    assert cc.freezers(tmp_path) == ["tests/x/test_a_new_event_survives_a_rename.py"]


def test_a_dry_run_prints_the_plan_and_clones_nothing(capsys, monkeypatch):
    monkeypatch.setattr(cc, "clone", lambda *a, **k: (_ for _ in ()).throw(AssertionError("a dry run cloned")))
    assert cc.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("ruff") and "tests/watchdog.py tests/infrastructure" in out


def test_a_failed_step_fails_the_check(monkeypatch, tmp_path):
    """The exit code is the verdict: one red step and the command says so, after running the rest."""
    calls = []

    def fake_clone(dest, *, ref, remote):
        (dest).mkdir(parents=True)
        (dest / "tests").mkdir()
        return "abc1234"

    class R:
        def __init__(self, code):
            self.returncode = code

    monkeypatch.setattr(cc, "clone", fake_clone)
    monkeypatch.setattr(cc.subprocess, "run", lambda cmd, cwd=None, **k: (calls.append(cmd[2] if len(cmd) > 2 else cmd),
                                                                         R(1 if "ruff" in cmd else 0))[1])
    assert cc.main(["--dest-root", str(tmp_path)]) == 1
    assert len(calls) == 4, "every step still runs, so one command reports every red"


def test_the_disarm_the_same_run_with_every_step_green_passes(monkeypatch, tmp_path):
    """The counter-case of the test above: the verdict follows the steps' exit codes, nothing else — all green, exit 0."""
    monkeypatch.setattr(cc, "clone", lambda dest, **k: (dest.mkdir(parents=True), (dest / "tests").mkdir(), "x")[2])

    class R:
        returncode = 0

    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: R())
    assert cc.main(["--dest-root", str(tmp_path)]) == 0


def test_the_clone_is_never_made_under_the_system_temp():
    """Measured on the first run: under `$TMPDIR` the clone shares its parent with every pytest `tmp_path`, and a test
    that runs pytest on a generated file gets that crowded dir as its rootdir (the watchdog's own tests hit 40 s)."""
    import tempfile
    default = cc.DEST_ROOT.expanduser().resolve()
    tmp = pathlib.Path(tempfile.gettempdir()).resolve()
    assert tmp not in default.parents and default != tmp
