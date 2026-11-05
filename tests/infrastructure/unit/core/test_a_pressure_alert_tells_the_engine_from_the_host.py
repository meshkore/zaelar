"""A pressure alert tells the engine's footprint from the host's (V2-852 T15).

The first live session on the task engine: ten «not answering or short of memory» alert pairs in six minutes. Every
one carried `rss_mb` ~300 and `loop_age_s` 0, and the host's free ratio on the floor — yet the record could not say
whether the browsers and the worker the engine started were the ones holding the memory, or something outside it (a
local model pinned on the GPU, which lives in no process's RSS). The `pressure` block now carries `tree_mb` (this
process and everything it started) and, where the platform reports it, `wired_mb`.

Disarm: drop `out["tree_mb"]` in `observability/pressure.snapshot` → red.
"""
from __future__ import annotations

import os
import subprocess
import sys


def test_the_footprint_counts_what_the_engine_started():
    from observability import pressure
    child = subprocess.Popen([sys.executable, "-c", "b = bytearray(64 * 2**20); import time; time.sleep(30)"])
    try:
        import psutil
        proc = psutil.Process(child.pid)
        for _ in range(50):                                   # until the child has touched its 64 MB
            if proc.memory_info().rss > 60 * 2**20:
                break
            import time
            time.sleep(0.05)
        snap = pressure.snapshot()
        own = psutil.Process(os.getpid()).memory_info().rss / 2**20
        assert snap["tree_mb"] >= own + 60, snap
        assert snap["tree_mb"] >= snap["rss_mb"]
    finally:
        child.kill()
        child.wait()


def test_a_host_that_pins_memory_says_how_much():
    import psutil
    from observability import pressure
    snap = pressure.snapshot()
    if getattr(psutil.virtual_memory(), "wired", None) is None:
        assert "wired_mb" not in snap, "a number the platform does not report is left out, never invented"
    else:
        assert snap["wired_mb"] > 0
