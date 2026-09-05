# The widget generator runs CONFINED: scratch cwd, write-jail, no CLAUDE.md in sight (V2-601 T-04, 2026-09-05).
#
# What the audit measured: `_run_agent` spawned the headless CLI with cwd = the REPO ROOT, so every generation
# auto-loaded `engine/CLAUDE.md` AND the parent workspace `CLAUDE.md` — the PRIVATE business one — and shipped
# both to whichever external endpoint serves the generation (Z.AI in production), at ~150k tokens of spawn cost
# per request (V2-117's numbers for the identical fault on workers). And its confinement was PROMPT-ONLY:
# probed against the real CLI, `--allowedTools "Write Edit Read"` + acceptEdits happily writes an ABSOLUTE path
# outside the cwd, so a contaminated spec could write anywhere undetected.
#
# The contract now: cwd is a private scratch dir with no CLAUDE.md above it; writes are confined MECHANICALLY by
# the dev worker's PreToolUse jail (`nucleo/dev_worker_guard`, ZAELAR_DEV_WORKER_ROOT = the target folder); and a
# jail that cannot be written refuses to start the agent (T-09's doctrine: a jail that degrades to a warning is a
# convention, not a control).
#
# Run: .venv/bin/pytest tests/browser/unit/widgets/test_generator_runs_confined.py -q
import json
import os
from pathlib import Path

from widgets import generator


class _FakeProc:
    returncode = 0

    def communicate(self, input=None, timeout=None):
        return "", ""

    def kill(self):
        pass


def _spawn_and_capture(monkeypatch, tmp_path):
    seen = {}

    def fake_popen(cmd, cwd=None, env=None, **kw):
        seen.update(cmd=cmd, cwd=cwd, env=env)
        # capture what exists AT SPAWN TIME — the settings file is deleted in _run_agent's finally
        if "--settings" in cmd:
            sp = cmd[cmd.index("--settings") + 1]
            seen["settings_at_spawn"] = Path(sp).read_text(encoding="utf-8") if os.path.exists(sp) else None
        return _FakeProc()

    monkeypatch.setattr(generator.subprocess, "Popen", fake_popen)
    target = tmp_path / "widgets" / "mi-widget"
    target.mkdir(parents=True)
    ok, err = generator._run_agent("build it", target=str(target))
    assert ok, err
    return seen, target


def test_the_cwd_has_no_claude_md_above_it(monkeypatch, tmp_path):
    seen, _ = _spawn_and_capture(monkeypatch, tmp_path)
    cwd = Path(seen["cwd"]).resolve()
    assert cwd != Path(generator.ZAELAR).resolve(), "cwd is the repo root again — the private context leak"
    walker = cwd
    while True:
        assert not (walker / "CLAUDE.md").exists(), \
            f"a CLAUDE.md at {walker} would be auto-loaded into every generation request"
        if walker.parent == walker:
            break
        walker = walker.parent


def test_the_write_jail_is_armed_at_spawn(monkeypatch, tmp_path):
    seen, target = _spawn_and_capture(monkeypatch, tmp_path)
    env, cmd = seen["env"], seen["cmd"]
    assert env.get("ZAELAR_DEV_WORKER_ROOT") == str(target.resolve()), "jail root not pointed at the target"
    assert "--settings" in cmd and "--add-dir" in cmd
    assert cmd[cmd.index("--add-dir") + 1] == str(target.resolve())
    hook = json.loads(seen["settings_at_spawn"] or "{}")
    matchers = [h.get("matcher", "") for h in hook.get("hooks", {}).get("PreToolUse", [])]
    assert any("Write" in m for m in matchers), "the settings file carries no PreToolUse Write matcher"
    # …and the hook can RESOLVE: the scratch cwd holds no code, so the engine root must ride PYTHONPATH.
    assert generator.ZAELAR in (env.get("PYTHONPATH") or "").split(os.pathsep), \
        "without the engine root on PYTHONPATH, `python -m nucleo.dev_worker_guard` cannot import"


def test_an_unwritable_jail_refuses_to_start(monkeypatch, tmp_path):
    """Fail-CLOSED: no settings file, no agent — never a warning and an unjailed run."""
    from nucleo import dev_worker_guard

    def boom(path, **kw):
        raise OSError("disk says no")
    monkeypatch.setattr(dev_worker_guard, "write_settings_file", boom)
    spawned = {}
    monkeypatch.setattr(generator.subprocess, "Popen",
                        lambda *a, **kw: spawned.update(yes=True) or _FakeProc())
    target = tmp_path / "w"
    target.mkdir()
    ok, err = generator._run_agent("build it", target=str(target))
    assert not ok and "jail" in err
    assert not spawned, "the agent started WITHOUT its jail"


def test_the_prompt_folder_is_absolute(tmp_path):
    """The cwd is a scratch dir now, so a relative folder ref would resolve against nothing."""
    d = str(tmp_path / "widgets" / "x")
    assert os.path.isabs(generator._folder_ref(d))
