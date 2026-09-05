# Ingestion runs on ONE loop, wherever it was fired from (V2-601 T-06, audit 2026-09-05).
#
# `ingest_utterance` is fired from BOTH event loops — the voice job-thread's (nucleo.py) and uvicorn's (probe,
# widgets ctx.ingest, messaging) — and its serializing `asyncio.Lock` cannot span loops: the audit reproduced
# that an UNCONTENDED cross-loop acquire never breaks (why this never blew up loudly), while a CONTENDED one
# hangs the waiter forever and poisons the lock — after which every contended ingest raises RuntimeError inside
# a fire-and-forget task, i.e. memory writes silently lost until restart. The fix is the engine's own INI-012
# rule: cross-loop work MARSHALS (`run_coroutine_threadsafe`, the browser_search/energy_meter/identity pattern)
# onto the home loop the server lifespan registers.
#
# Run: .venv/bin/pytest tests/memory/unit/test_ingest_runs_on_one_loop.py -q
import asyncio
import threading

from nucleo.memory_agent import ingest


def _home_loop():
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()
    return loop, t


def test_a_foreign_caller_lands_on_the_home_loop(monkeypatch):
    home, _t = _home_loop()
    seen = {}

    async def spy(text, *, role="operator"):
        seen["loop"] = asyncio.get_running_loop()
        return {"source": "spy", "atoms": 0}
    monkeypatch.setattr(ingest, "_ingest_utterance_locked", spy)
    monkeypatch.setattr(ingest, "_HOME_LOOP", home)
    try:
        out = asyncio.run(ingest.ingest_utterance("hola"))
        assert out["source"] == "spy"
        assert seen["loop"] is home, "the ingest body ran on the CALLER's loop — the lock spans loops again"
    finally:
        home.call_soon_threadsafe(home.stop)


def test_two_contending_callers_from_two_loops_both_finish(monkeypatch):
    """The audited failure shape: contention across loops. Marshalled, both complete; unmarshalled this is the
    hang-forever/poison case."""
    home, _t = _home_loop()
    done = []

    async def slow(text, *, role="operator"):
        await asyncio.sleep(0.05)
        done.append(text)
        return {"source": "slow", "atoms": 0}
    monkeypatch.setattr(ingest, "_ingest_utterance_locked", slow)
    monkeypatch.setattr(ingest, "_HOME_LOOP", home)

    def call(text):
        return asyncio.run(asyncio.wait_for(ingest.ingest_utterance(text), timeout=5))
    try:
        t1 = threading.Thread(target=call, args=("uno",))
        t2 = threading.Thread(target=call, args=("dos",))
        t1.start(); t2.start()
        t1.join(timeout=6); t2.join(timeout=6)
        assert sorted(done) == ["dos", "uno"], f"a contended cross-loop ingest was lost: {done}"
    finally:
        home.call_soon_threadsafe(home.stop)


def test_without_a_registered_loop_nothing_changes(monkeypatch):
    """Unit tests and standalone runs never call set_loop — a single-loop process keeps today's behavior."""
    called = {}

    async def spy(text, *, role="operator"):
        called["loop"] = asyncio.get_running_loop()
        return {"source": "spy", "atoms": 0}
    monkeypatch.setattr(ingest, "_ingest_utterance_locked", spy)
    monkeypatch.setattr(ingest, "_HOME_LOOP", None)

    async def go():
        out = await ingest.ingest_utterance("hola")
        assert called["loop"] is asyncio.get_running_loop()
        return out
    assert asyncio.run(go())["source"] == "spy"


def test_the_lifespan_wires_the_home_loop():
    """The marshal is only real if the server registers the loop (V2-199: the wiring is the fix)."""
    import re
    from pathlib import Path
    src = (Path(__file__).resolve().parents[3] / "server" / "__init__.py").read_text(encoding="utf-8")
    src = re.sub(r"(?m)#.*$", "", src)
    assert "_mem_agent.set_loop(_running_loop)" in src
