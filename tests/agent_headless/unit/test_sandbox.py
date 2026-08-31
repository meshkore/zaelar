#
# Lightweight execution sandbox (V2-076 Part B). Run: .venv/bin/pytest tests/agent_headless/unit/test_sandbox.py -q
#
# Ensures that created code can be EXECUTED for auditing without casually compromising the host:
# isolated subprocess (temporary cwd + scrubbed env + limits + timeout). Supports Python + SQLite.
#
import os

from nucleo import sandbox


def test_runs_python_and_captures_stdout():
    r = sandbox.run("print('hola sandbox')")
    assert r["ok"] and r["exit"] == 0
    assert "hola sandbox" in r["stdout"]


def test_supports_sqlite():
    code = ("import sqlite3; c=sqlite3.connect(':memory:'); c.execute('create table t(x)'); "
            "c.execute('insert into t values (42)'); print(c.execute('select x from t').fetchone()[0])")
    r = sandbox.run(code)
    assert r["ok"] and "42" in r["stdout"]


def test_error_is_captured_not_raised():
    r = sandbox.run("raise ValueError('boom')")
    assert not r["ok"] and r["exit"] != 0
    assert "ValueError" in r["stderr"] and "boom" in r["stderr"]


def test_timeout_kills_process():
    r = sandbox.run("import time; time.sleep(10)", timeout=1.0)
    assert r["timed_out"] is True and not r["ok"]
    assert r["elapsed_s"] < 5           # it was killed promptly; it did not wait the 10s


def test_env_is_scrubbed_no_secret_leak():
    os.environ["ZAELAR_SANDBOX_TEST_SECRET"] = "no-debe-verse"
    try:
        r = sandbox.run("import os; print('SECRET=' + repr(os.environ.get('ZAELAR_SANDBOX_TEST_SECRET')))")
        assert "SECRET=None" in r["stdout"]     # the subprocess does NOT see the parent's secrets/ZAELAR_*
    finally:
        os.environ.pop("ZAELAR_SANDBOX_TEST_SECRET", None)


def test_runs_in_temp_workdir_not_project():
    r = sandbox.run("import os; print(os.getcwd())")
    cwd = r["stdout"].strip()
    assert "zaelar-sbx-" in cwd            # it runs in a dedicated temporary directory, not the project root


def test_unsupported_lang_degrades():
    r = sandbox.run("fn main(){}", lang="rust")
    assert not r["ok"] and "no soportado" in r["stderr"]


# ── interactive dev-worker rlimits (2026-07-26 audit, different from those of run()) ────────────────────────
def test_dev_worker_rlimits_sets_limits_without_erroring():
    """Unlike `_rlimits()` (short CPU/wall limits for a one-turn script), these must NOT limit time —
    only memory/nproc/fsize. Confirms that preexec_fn NEVER crashes the subprocess (each setrlimit is in its
    own try/except) and that `RLIMIT_NPROC` (which DOES apply on Linux AND macOS, empirically verified) is
    actually set. **`RLIMIT_AS` (memory) is intentionally NOT checked here**: on macOS/Darwin,
    `setrlimit(RLIMIT_AS, …)` raises `ValueError` (Darwin does not support limiting the address space) — it is
    a silent no-op there, as honestly documented in the `dev_worker_rlimits()` docstring, not a failure of this test."""
    import subprocess
    import sys

    apply_fn = sandbox.dev_worker_rlimits()
    if apply_fn is None:
        return   # Windows or another platform without `resource` — same honest limitation as _rlimits()
    code = "import resource; print(resource.getrlimit(resource.RLIMIT_NPROC)[0])"
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       preexec_fn=apply_fn, timeout=10)
    assert p.returncode == 0
    assert str(sandbox._DEV_NPROC) in p.stdout


def test_dev_worker_rlimits_compatible_with_start_new_session():
    """Must not conflict with `start_new_session=True` (claude_session.py ALWAYS uses it, for the group killpg) —
    reproduces the SAME combination in a real, isolated subprocess (never in the test process itself: applying
    a memory/nproc rlimit to the pytest runner would break the rest of the suite)."""
    import subprocess
    import sys

    apply_fn = sandbox.dev_worker_rlimits()
    if apply_fn is None:
        return
    p = subprocess.run([sys.executable, "-c", "print('ok')"], capture_output=True, text=True,
                       preexec_fn=apply_fn, start_new_session=True, timeout=10)
    assert p.returncode == 0 and "ok" in p.stdout
