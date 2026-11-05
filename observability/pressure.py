"""observability/pressure.py — the numbers behind a pressure alert (V2-837 G8).

The self-watchdog's alert carried `free_ratio`; the «low memory» worker notice and `homeostasis degraded` carried
nothing, so «the engine was out of memory» could not be told from «a browser was stuck» on the record. Every
`alert` and `homeostasis` event now carries ONE `pressure` block, stamped at the observer's door
(`voice/observer.emit`), never by each caller:

    rss_mb      this process's resident memory
    tree_mb     this process AND everything it started (browsers, workers, helpers): the engine's whole footprint
    free_mb     the host's available memory          free_ratio   that, over the host total
    wired_mb    memory the host's kernel has pinned (where the platform reports it): a local model held on the GPU
                lives here and in no process's RSS, so a host short of memory with a small `tree_mb` and a large
                `wired_mb` was starved by something outside the engine
    browsers    live browser processes under this engine (a browser's helper processes are not counted)
    workers     live Brain Worker sessions

Measured (V2-852 T15, the first live session on the task engine): ten shed/recovered alert pairs in six minutes, every
one with `rss_mb` 245-377 and `loop_age_s` 0 — the engine was answering and small; the host's free ratio sat on the
floor (0.095-0.14) with a 44 GB local model resident outside the engine. `rss_mb` alone could not say that the rest
of the engine (two browsers, one worker) was small too, nor where the host's memory was.

Measured when the event is emitted (alerts are rare); every part is fail-soft — a number that cannot be read is left
out, never invented.
"""
from __future__ import annotations

from loguru import logger

import os


def _browsers(proc) -> int:
    n = 0
    for c in proc.children(recursive=True):
        try:
            name = (c.name() or "").lower()
            if "chrom" not in name and "headless_shell" not in name:
                continue
            if any(a.startswith("--type=") for a in (c.cmdline() or [])):
                continue                        # a renderer/GPU/utility helper of a browser already counted
            n += 1
        except Exception as e:  # noqa: BLE001 — a process that ended or is not ours to read
            logger.debug(f"pressure._browsers: {e!r}")
            continue
    return n


def _tree_mb(proc, own_rss: int) -> int:
    total = own_rss
    for c in proc.children(recursive=True):
        try:
            total += c.memory_info().rss
        except Exception as e:  # noqa: BLE001 — a process that ended or is not ours to read
            logger.debug(f"pressure._tree_mb: {e!r}")
    return round(total / 2**20)


def _workers() -> int | None:
    try:
        from nucleo import dispatch as _d
        return sum(1 for r in list(_d._SESSIONS.values()) if getattr(r, "status", "") in _d.LIVE_SESSION_STATES)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pressure._workers: {e!r}")
        return None


def snapshot() -> dict:
    out: dict = {}
    try:
        import psutil
        me = psutil.Process(os.getpid())
        rss = me.memory_info().rss
        out["rss_mb"] = round(rss / 2**20)
        out["tree_mb"] = _tree_mb(me, rss)
        vm = psutil.virtual_memory()
        out["free_mb"] = round(vm.available / 2**20)
        out["free_ratio"] = round(vm.available / vm.total, 3) if vm.total else None
        if getattr(vm, "wired", None) is not None:
            out["wired_mb"] = round(vm.wired / 2**20)
        out["browsers"] = _browsers(me)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pressure.snapshot: {e!r}")
        pass
    out["workers"] = _workers()
    return {k: v for k, v in out.items() if v is not None}
