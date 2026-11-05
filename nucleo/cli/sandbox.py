#
# sandbox.py — the resource limits of the INTERACTIVE dev-worker subprocess (V2-076; audit 2026-07-26). The one-turn
# script runner that used to live here (`run()`, its short CPU/wall limits and its scrubbed env) had no caller left
# and went in the V2-851 deletion pass.
#
from __future__ import annotations

import os


# ── rlimits for the INTERACTIVE dev-worker subprocess (audit 2026-07-26) ─────────────────────────────────────────
# Unlike a single-turn script (short wall/CPU limits), an interactive dev-worker
# (nucleo/workers/providers/claude.py, a session that may legitimately last minutes) must NOT inherit that short CPU/wall
# limit — its lifecycle is already governed by dispatch.py (its own timeouts/cancellation), not an rlimit. What DOES make
# sense to limit without a time limit: memory, number of processes, and file size — defense in depth against
# a runaway/fork bomb, without risking killing a real task halfway through.
_DEV_MEM_MB = int(os.getenv("ZAELAR_DEV_WORKER_MEM_MB", "2048"))
_DEV_NPROC = int(os.getenv("ZAELAR_DEV_WORKER_NPROC", "128"))
_DEV_FSIZE_MB = int(os.getenv("ZAELAR_DEV_WORKER_FSIZE_MB", "512"))


def dev_worker_rlimits():
    """preexec_fn for the dev-worker subprocess. Mac/Linux only (Windows has no `resource`). Does NOT call `os.setsid()`: `claude_session.py` already passes `start_new_session=True`
    (its own group for `killpg`); duplicating it here could conflict with that.

    HONEST LIMIT (empirically verified, not falsely reassuring): on macOS/Darwin `resource.setrlimit(RLIMIT_AS, …)`
    raises `ValueError: current limit exceeds maximum limit` — Darwin does NOT support limiting a process's address space
    this way, period (it is not "more permissive"; it is a silent no-op, caught by the `except` below). The MEMORY limit
    provides real protection only on Linux (cloud production). `RLIMIT_NPROC` and `RLIMIT_FSIZE` DO apply
    on both (verified). REAL protection against exfiltration/reading outside the cwd on ANY platform
    is the path jail (`nucleo/dev_worker_guard.py`, PreToolUse hook), not this rlimit."""
    try:
        import resource
    except Exception:
        return None

    def _apply():
        try:
            b = _DEV_MEM_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (_DEV_NPROC, _DEV_NPROC))
        except Exception:
            pass
        try:
            b = _DEV_FSIZE_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_FSIZE, (b, b))
        except Exception:
            pass
    return _apply
