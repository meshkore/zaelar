"""An on-demand order wakes the email connector instead of waiting out its poll (demo pass 31, E2, 2026-09-28).

«did inworld send me something?» asked the mailbox for the receipt; «open it» came 14 s later and failed; the mail
landed 3 s after that — the history order had waited out the 20 s poll interval.
"""
import asyncio
import time

from connectors.email import service


class _Inbox:
    def __init__(self):
        self.has = False

    def pending(self):
        return self.has


def test_a_history_order_cuts_the_nap_short(monkeypatch):
    hist = _Inbox()
    monkeypatch.setattr(service, "_history_inbox", hist)
    monkeypatch.setattr(service, "_send_inbox", None)
    monkeypatch.setattr(service, "_fetch_inbox", None)

    async def run():
        async def arrive():
            await asyncio.sleep(0.3)
            hist.has = True
        t = time.monotonic()
        await asyncio.gather(service._nap(20), arrive())
        return time.monotonic() - t
    assert asyncio.run(run()) < 2.0


def test_with_nothing_pending_it_sleeps_the_whole_interval(monkeypatch):
    for n in ("_history_inbox", "_send_inbox", "_fetch_inbox"):
        monkeypatch.setattr(service, n, None)
    t = time.monotonic()
    asyncio.run(service._nap(1.0))
    assert time.monotonic() - t >= 0.95
