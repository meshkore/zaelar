"""Every trusted worker that may WRITE is jailed to its own workdir (V2-778 F4-34, 2026-10-01).

The dev-worker of a cluster has had a real jail since V2-076: a PreToolUse hook that denies a path outside its
temporary cwd. The ordinary trusted worker — web, research, monitor — got `Write` in 2026-08-28 (the bridge
payloads travel through a file it writes) and no jail: Claude Code confines Write/Edit to the cwd by default, and
that default was the only thing between a worker steered by a hostile page and `Write ~/.zshrc`. The audit asked
for the same hook on that branch. Reads stay free on purpose: these workers read captures and inputs outside
their workdir (`read_dirs`), so the hook runs in WRITES-ONLY mode there.
"""
from __future__ import annotations

import os

from nucleo import dev_worker_guard as g


def _payload(tool, path, cwd):
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: path}, "cwd": cwd}


def test_in_writes_only_mode_a_write_outside_the_workdir_is_denied_and_a_read_is_not(tmp_path, monkeypatch):
    wd = tmp_path / "task"; wd.mkdir()
    monkeypatch.setenv("ZAELAR_DEV_WORKER_ROOT", str(wd))
    monkeypatch.setenv("ZAELAR_JAIL_WRITES_ONLY", "1")
    home = os.path.expanduser("~/x")
    assert g.check(_payload("Write", home, str(wd))) is False, "Write ~/x has to be denied"
    assert g.check(_payload("Edit", "/etc/hosts", str(wd))) is False
    assert g.check(_payload("Write", "informe.json", str(wd))) is True, "its own relative file is its job"
    assert g.check(_payload("Read", "/etc/hosts", str(wd))) is True, "reads stay free for this kind of worker"
    assert g.check(_payload("Glob", "/", str(wd))) is True


def test_the_dev_worker_keeps_its_full_jail(tmp_path, monkeypatch):
    wd = tmp_path / "dev"; wd.mkdir()
    monkeypatch.setenv("ZAELAR_DEV_WORKER_ROOT", str(wd))
    monkeypatch.delenv("ZAELAR_JAIL_WRITES_ONLY", raising=False)
    assert g.check(_payload("Read", "/etc/hosts", str(wd))) is False, "the dev-worker's reads stay jailed"


def test_arming_the_jail_sets_the_root_the_mode_and_the_settings(tmp_path):
    wd = tmp_path / "task"; wd.mkdir()
    env: dict = {}
    tools, extra = g.jail_writes(["Read", "Write", "WebSearch"], str(wd), env, key="t1", settings_dir=str(tmp_path))
    assert tools == ["Read", "Write", "WebSearch"]
    assert env["ZAELAR_DEV_WORKER_ROOT"] == str(wd) and env["ZAELAR_JAIL_WRITES_ONLY"] == "1"
    assert extra[0] == "--settings" and os.path.isfile(extra[1]), extra
    assert not os.path.realpath(extra[1]).startswith(os.path.realpath(str(wd))), \
        "the settings live OUTSIDE the workdir, or the worker could rewrite its own jail"


def test_a_jail_that_cannot_be_written_takes_the_pen_away_not_the_worker(tmp_path):
    wd = tmp_path / "task"; wd.mkdir()
    tools, extra = g.jail_writes(["Read", "Write", "Edit", "WebSearch"], str(wd), {}, key="t2",
                                 settings_dir=str(tmp_path / "missing" / "dir"))
    assert tools == ["Read", "WebSearch"] and extra == [], "fail closed for WRITING only"


def test_a_worker_without_write_is_left_alone(tmp_path):
    env: dict = {}
    tools, extra = g.jail_writes(["Read", "WebSearch"], str(tmp_path), env, key="t3", settings_dir=str(tmp_path))
    assert tools == ["Read", "WebSearch"] and extra == [] and env == {}


def test_the_session_arms_it_for_every_trusted_worker_with_a_workdir():
    from tests import voice_turn_source as _vts
    from nucleo import dispatch
    src = _vts.getsource(dispatch._run_session)
    assert "dev_worker_guard.jail_writes(" in src, "the ordinary worker's spec is built without the jail"


def test_the_hook_denies_when_run_the_way_the_cli_runs_it(tmp_path):
    """A hook that cannot import its module fails OPEN in the CLI (a hook error does not block the tool), so a jail
    whose command does not resolve is inert and silent. Run it as the CLI does: from the worker's own cwd, with the
    env the session gives it (`workdir.env_for_task` puts the engine on PYTHONPATH)."""
    import json
    import subprocess
    import sys
    from nucleo.workers import workdir
    wd = tmp_path / "task"; wd.mkdir()
    env = {"PATH": os.environ.get("PATH", ""), **workdir.env_for_task({})}
    tools, extra = g.jail_writes(["Read", "Write"], str(wd), env, key="t4", settings_dir=str(tmp_path))
    cmd = json.load(open(extra[1]))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    payload = json.dumps(_payload("Write", os.path.expanduser("~/x"), str(wd)))
    out = subprocess.run(cmd, shell=True, input=payload, capture_output=True, text=True, cwd=str(wd), env=env, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny", out.stdout
    ok = subprocess.run(cmd, shell=True, input=json.dumps(_payload("Read", "/etc/hosts", str(wd))),
                        capture_output=True, text=True, cwd=str(wd), env=env, timeout=30)
    assert json.loads(ok.stdout) == {}, "a read passes"
    assert sys.executable  # the command is the engine's own interpreter
