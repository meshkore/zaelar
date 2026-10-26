"""A use-case sandbox boots beside the operator's running engine (2026-10-27).

`nucleo/one_engine.py` (2026-10-21) makes a local engine take an OS lock in `~/.zaelar/` and refuse to boot while
another holds it. Every sandbox inherited that path, so with his engine up no sandbox could boot — «another zaelar
engine is already running on this machine» — and no use case ran for twelve days without anyone noticing, because
the last round predated the lock. The lock guards what an engine OWNS (the voice worker slot, the fixed ports, the
connectors' pollers); a sandbox owns none of them, so it takes its own lock inside its throwaway workspace.

The first test reads the environment `Popen` would receive; the second takes both locks for real in one process.
"""
from __future__ import annotations

import os
from pathlib import Path

from tests.platform import sandbox_engine as SE


class _FakeProc:
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, *a, **k):
        pass

    def kill(self):
        pass


def _env(monkeypatch) -> tuple[dict, Path]:
    seen: dict = {}

    def _popen(argv, **kw):
        seen["env"] = kw.get("env") or {}
        return _FakeProc()

    monkeypatch.setattr(SE.subprocess, "Popen", _popen)
    monkeypatch.setattr(SE, "_wait_ready", lambda eng, timeout: None)
    with SE.sandbox_engine() as eng:
        return seen["env"], eng.workspace


def test_the_sandbox_takes_its_lock_inside_its_own_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_LOCK_DIR", str(tmp_path / "operator-home"))     # the host's lock, wherever it is
    env, ws = _env(monkeypatch)
    lock = env.get("ZAELAR_LOCK_DIR")
    assert lock and Path(lock).is_relative_to(ws), f"the sandbox would meet the operator's lock: {lock!r}"


def test_two_lock_dirs_are_two_locks(tmp_path, monkeypatch):
    """The lock is per directory: the operator's engine holding his does not stop a sandbox taking its own."""
    import subprocess
    import sys
    held = tmp_path / "operator"
    code = ("import sys; sys.path.insert(0, %r); from nucleo import one_engine as o; "
            "print(o.hold(%r)); sys.stdout.flush(); sys.stdin.read()") % (str(SE.ENGINE), str(SE.ENGINE))
    holder = subprocess.Popen([sys.executable, "-c", code], env={**os.environ, "ZAELAR_LOCK_DIR": str(held)},
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "None", "the holder could not take its lock"
        from nucleo import one_engine as o
        monkeypatch.setattr(o, "_held", o._held)    # the lock this test takes is given back below, not kept
        monkeypatch.setenv("ZAELAR_LOCK_DIR", str(held))
        assert o.hold(str(SE.ENGINE)) is not None, "the operator's lock must refuse a second engine there"
        monkeypatch.setenv("ZAELAR_LOCK_DIR", str(tmp_path / "sandbox"))
        assert o.hold(str(SE.ENGINE)) is None, "a sandbox's own lock dir must be free"
        o._held.close()
    finally:
        holder.stdin.close()
        holder.wait(timeout=10)
