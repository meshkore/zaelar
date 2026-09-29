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
