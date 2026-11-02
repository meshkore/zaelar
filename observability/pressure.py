"""observability/pressure.py — the numbers behind a pressure alert (V2-837 G8).

The self-watchdog's alert carried `free_ratio`; the «low memory» worker notice and `homeostasis degraded` carried
nothing, so «the engine was out of memory» could not be told from «a browser was stuck» on the record. Every
`alert` and `homeostasis` event now carries ONE `pressure` block, stamped at the observer's door
(`voice/observer.emit`), never by each caller:

    rss_mb      this process's resident memory
    free_mb     the host's available memory          free_ratio   that, over the host total
    browsers    live browser processes under this engine (a browser's helper processes are not counted)
    workers     live Brain Worker sessions

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
        out["rss_mb"] = round(me.memory_info().rss / 2**20)
        vm = psutil.virtual_memory()
        out["free_mb"] = round(vm.available / 2**20)
        out["free_ratio"] = round(vm.available / vm.total, 3) if vm.total else None
        out["browsers"] = _browsers(me)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"pressure.snapshot: {e!r}")
        pass
    out["workers"] = _workers()
    return {k: v for k, v in out.items() if v is not None}
