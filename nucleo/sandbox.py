#
# sandbox.py — ISOLATED and LIGHTWEIGHT execution of generated code (V2-076, Part B). The EASIEST and lightest (operator
# decision), cross-platform Win/Mac, instant startup, with no extra runtime: a bounded ephemeral SUBPROCESS. Supports
# Python + SQLite (stdlib) out of the box. Docker is NOT the default (resource-heavy/problematic); it remains a future
# fallback for strong isolation or heavyweight toolchains (e.g. Rust).
#
# Isolation is provided by: (1) a dedicated TEMPORARY working directory (cwd there; code sees only that directory); (2) a SCRUBBED
# environment (only minimal PATH/HOME/LANG — no secrets, API keys, or ZAELAR_*); (3) RESOURCE limits (CPU, memory,
# files, processes) via `resource.setrlimit` on Mac/Linux; (4) a wall-clock TIMEOUT that kills the process group.
#
# HONEST LIMIT (documented, not falsely reassuring): a subprocess is NOT bulletproof kernel isolation —
# it does not hard-block the NETWORK cross-platform or prevent all disk access outside the cwd via absolute paths.
# It is the first "lightweight" level for AUDITING/observing generated code without casually compromising the host; the
# strong hardening (container/micro-VM without network, read-only FS) is the next step (Docker fallback).
#
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time

# Default limits (env-overridable, infrastructure).
_CPU_S = int(os.getenv("SANDBOX_CPU_S", "10"))            # CPU seconds
_WALL_S = float(os.getenv("SANDBOX_WALL_S", "15"))        # wall-clock seconds
_MEM_MB = int(os.getenv("SANDBOX_MEM_MB", "512"))         # memory (address space)
_OUT_MAX = int(os.getenv("SANDBOX_OUT_MAX", str(256 * 1024)))  # stdout/stderr truncation

# MINIMAL environment: nothing from the parent process except what is essential. No secrets/keys/ZAELAR_*.
_ENV_KEEP = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "PATHEXT")


def _clean_env() -> dict:
    return {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}


def _rlimits():
    """preexec_fn for Mac/Linux: limits CPU, memory (address space), number of files, and processes. On Windows
    returns None (there is no `resource`; the wall-clock timeout is the safety net)."""
    try:
        import resource
    except Exception:
        return None

    def _apply():
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (_CPU_S, _CPU_S + 1))
        except Exception:
            pass
        try:
            b = _MEM_MB * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (b, b))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except Exception:
            pass
        try:
            resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        except Exception:
            pass
        os.setsid()   # own group → can be killed as a unit on timeout
    return _apply


def run(code: str, *, lang: str = "python", stdin: str = "", timeout: float | None = None,
        workdir: str | None = None) -> dict:
    """Executes `code` in an ISOLATED subprocess and returns the result. Does NOT raise: always returns a dict
    {ok, exit, stdout, stderr, elapsed_s, timed_out, workdir}. Currently supports lang='python' (including SQLite)."""
    if lang != "python":
        return {"ok": False, "exit": -1, "stdout": "", "stderr": f"lang '{lang}' no soportado aún (solo python)",
                "elapsed_s": 0.0, "timed_out": False, "workdir": ""}
    owns_dir = workdir is None
    wd = workdir or tempfile.mkdtemp(prefix="zaelar-sbx-")
    src = os.path.join(wd, "main.py")
    with open(src, "w", encoding="utf-8") as f:
        f.write(code or "")
    wall = timeout or _WALL_S
    t0 = time.time()
    timed_out = False
    try:
        p = subprocess.run(
            [sys.executable, "-I", "main.py"],       # -I: isolated (ignores PYTHON* env, does not add the user's cwd)
            cwd=wd, input=stdin, capture_output=True, text=True,
            env=_clean_env(), timeout=wall,
            preexec_fn=_rlimits() if os.name != "nt" else None,
        )
        out, err, code_ = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired as e:
        timed_out = True
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        err = ((e.stderr or "") if isinstance(e.stderr, str) else "") + f"\n[sandbox] timeout {wall}s — proceso matado"
        code_ = -1
    except Exception as e:  # noqa: BLE001
        out, err, code_ = "", f"[sandbox] fallo al ejecutar: {type(e).__name__}: {e}", -1
    finally:
        if owns_dir:
            shutil.rmtree(wd, ignore_errors=True)
    return {"ok": (code_ == 0 and not timed_out), "exit": code_,
            "stdout": (out or "")[:_OUT_MAX], "stderr": (err or "")[:_OUT_MAX],
            "elapsed_s": round(time.time() - t0, 2), "timed_out": timed_out, "workdir": wd}


async def arun(code: str, **kwargs) -> dict:
    """Async wrapper (runs `run` outside the event loop) for async callers such as the dispatcher."""
    import asyncio
    return await asyncio.to_thread(run, code, **kwargs)


# ── rlimits for the INTERACTIVE dev-worker subprocess (audit 2026-07-26) ─────────────────────────────────────────
# `_rlimits()` above is tuned for `run()` (a single-turn script, with short wall/CPU limits): an interactive dev-worker
# (nucleo/workers/claude_session.py, a session that may legitimately last minutes) must NOT inherit that short CPU/wall
# limit — its lifecycle is already governed by dispatch.py (its own timeouts/cancellation), not an rlimit. What DOES make
# sense to limit without a time limit: memory, number of processes, and file size — defense in depth against
# a runaway/fork bomb, without risking killing a real task halfway through.
_DEV_MEM_MB = int(os.getenv("ZAELAR_DEV_WORKER_MEM_MB", "2048"))
_DEV_NPROC = int(os.getenv("ZAELAR_DEV_WORKER_NPROC", "128"))
_DEV_FSIZE_MB = int(os.getenv("ZAELAR_DEV_WORKER_FSIZE_MB", "512"))


def dev_worker_rlimits():
    """preexec_fn for the dev-worker subprocess. Mac/Linux only (Windows has no `resource` — same honest limit
    as `_rlimits()`). Does NOT call `os.setsid()`: `claude_session.py` already passes `start_new_session=True`
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
