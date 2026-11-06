# Ingestion runs on ONE loop, wherever it was fired from (V2-601 T-06, audit 2026-09-05).
#
# `ingest_utterance` is fired from BOTH event loops — the voice job-thread's (nucleo.py) and uvicorn's (probe,
# widgets ctx.ingest, messaging) — and its serializing `asyncio.Lock` cannot span loops: the audit reproduced
# that an UNCONTENDED cross-loop acquire never breaks (why this never blew up loudly), while a CONTENDED one
# hangs the waiter forever and poisons the lock — after which every contended ingest raises RuntimeError inside
# a fire-and-forget task, i.e. memory writes silently lost until restart. The fix is the engine's own
# rule: cross-loop work MARSHALS (`run_coroutine_threadsafe`, the browser_search/energy_meter/identity pattern)
# onto the home loop the server lifespan registers.
#
# Run: .venv/bin/pytest tests/memory/unit/test_ingest_runs_on_one_loop.py -q
import asyncio
import threading

from tests import voice_turn_source as _vts   # V2-778 F1: a split file is read with its moved pieces


def _home_loop():
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop, t


def test_the_lifespan_wires_the_home_loop():
    """The marshal is only real if the server registers the loop (V2-199: the wiring is the fix)."""
    import re
    from pathlib import Path
    src = _vts.read(Path(__file__).resolve().parents[3] / "server" / "boot" / "surfaces.py")
    src = re.sub(r"(?m)#.*$", "", src)
    assert "_mem_agent.set_loop(_running_loop)" in src
