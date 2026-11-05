#
# The dev-worker's resource limits (V2-076). Run: .venv/bin/pytest tests/agent_headless/unit/test_sandbox.py -q
#
from nucleo.cli import sandbox


# ── interactive dev-worker rlimits (2026-07-26 audit) ────────────────────────
def test_dev_worker_rlimits_sets_limits_without_erroring():
    """Unlike a one-turn script's short CPU/wall limits, these must NOT limit time —
    only memory/nproc/fsize. Confirms that preexec_fn NEVER crashes the subprocess (each setrlimit is in its
    own try/except) and that `RLIMIT_NPROC` (which DOES apply on Linux AND macOS, empirically verified) is
    actually set. **`RLIMIT_AS` (memory) is intentionally NOT checked here**: on macOS/Darwin,
    `setrlimit(RLIMIT_AS, …)` raises `ValueError` (Darwin does not support limiting the address space) — it is
    a silent no-op there, as honestly documented in the `dev_worker_rlimits()` docstring, not a failure of this test."""
    import subprocess
    import sys

    apply_fn = sandbox.dev_worker_rlimits()
    if apply_fn is None:
        return   # Windows or another platform without `resource` — no `resource` there
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
