"""Demo pass 48 (2026-09-29), E1→E3: the receipt's history order, asked at E1, reached the card 43 s later — the mail
loop ran its new-mail fetch, flag poll and the rest (each its own IMAP login) before it — and «open it» and the
forward had already failed. What the operator is waiting for (sends, history, fetch) runs first in every tick."""
import asyncio

from connectors.email import service


def test_history_is_drained_before_the_new_mail_fetch(monkeypatch):
    calls = []

    class _MB:
        def test_connection(self):
            return True, ""
    monkeypatch.setattr(service.config, "mailbox", lambda: _MB())
    monkeypatch.setattr(service, "seed_from_mailbox", lambda mb: None)
    monkeypatch.setattr(service, "_set_status", lambda *a, **k: None)
    monkeypatch.setattr(service.ingest, "v2_enabled", lambda: False)

    def rec(name, stop=False):
        async def _f(mb):
            calls.append(name)
            if stop:
                raise asyncio.CancelledError()
        return _f
    for n in ("_drain_sends", "_drain_history", "_drain_fetch", "_drain_reads", "_drain_replies",
              "_drain_disposals", "_drain_unreads", "_poll_external_flags"):
        monkeypatch.setattr(service, n, rec(n))
    monkeypatch.setattr(service, "_ingest_new", rec("_ingest_new", stop=True))
    try:
        asyncio.run(service._loop())
    except asyncio.CancelledError:
        pass
    assert "_drain_history" in calls and calls.index("_drain_history") < calls.index("_ingest_new"), calls
    assert service._demand_task is not None, "the loop never started the on-demand server beside it"
    service._demand_task = None


def test_an_order_arriving_mid_tick_is_served_beside_it(monkeypatch):
    """…and one that arrives while a tick is busy is not held for the rest of it: a demand loop beside the poll
    serves it at once."""
    served = []

    class _Inbox:
        def __init__(self):
            self.n = 1

        def pending(self):
            return self.n > 0
    inbox = _Inbox()
    monkeypatch.setattr(service, "_history_inbox", inbox)

    async def _hist(mb):
        served.append("history")
        inbox.n = 0

    async def _noop(mb):
        return None
    monkeypatch.setattr(service, "_drain_history", _hist)
    monkeypatch.setattr(service, "_drain_sends", _noop)
    monkeypatch.setattr(service, "_drain_fetch", _noop)

    async def run():
        t = asyncio.create_task(service._serve_demands(object()))
        await asyncio.sleep(0.2)
        t.cancel()
    asyncio.run(run())
    assert served == ["history"]
