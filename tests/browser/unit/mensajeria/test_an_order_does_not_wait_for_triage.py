"""Demo pass 45 (2026-09-29), E1→E3: «did inworld send me something?» queued the receipt's history fetch, and it left
two minutes later — E2 «open it» and E3 «send the invoice to quinn» had already failed on a card that did not hold
it. The owner's loop was parked in `_triage_batch`, whose announcement waits for silence in a conversation that had
none. The operator's queued orders are flushed every tick, whatever triage is doing."""
import asyncio
import queue

from widgets.mensajeria import owner


def test_a_history_order_leaves_while_triage_hangs(monkeypatch):
    monkeypatch.setattr(owner, "_BATCH", 0.02)
    published, orders = [], [[{"platform": "email", "chatId": "invoice@inworld.ai", "beforeId": "220441"}]]

    async def _hang(*a, **k):
        await asyncio.sleep(60)
        return []
    from widgets.mensajeria import triage_agent
    monkeypatch.setattr(triage_agent, "classify", _hang)
    monkeypatch.setattr(owner.msgstore, "take_pending_history", lambda *a: orders.pop() if orders else [])
    monkeypatch.setattr(owner.ingest, "publish_history_ask", lambda o: published.append(o))
    o = owner._Owner()
    q = queue.Queue()
    q.put({"platform": "email", "body": "a new mail to triage"})
    o._msg_sub = type("S", (), {"queue": q})()

    async def run():
        task = asyncio.create_task(o._consume())
        await asyncio.sleep(0.3)
        task.cancel()
        if o._triage_task:
            o._triage_task.cancel()
    asyncio.run(run())
    assert published, "the history order waited behind a triage that never finished"
