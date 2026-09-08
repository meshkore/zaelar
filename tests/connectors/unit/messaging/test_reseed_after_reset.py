"""connectors/messaging/reseed.py — the fan-out `nucleo/reset.py::reset_all()` fires after blanking mensajería.

Only email gets a `reseed()` call today: WhatsApp/Telegram are live-push, drain-once architectures (a bridge
queue, a Telethon event) with no durable server-side "still unread" reservoir to re-poll, unlike IMAP — clearing
their dedup sets would be a no-op, so this module deliberately does not call one that does not exist.
"""
import pytest

from connectors.messaging import reseed


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_reseed_all_calls_email_when_it_is_enabled(monkeypatch):
    calls = []

    class _Email:
        @staticmethod
        def enabled():
            return True

        @staticmethod
        async def reseed():
            calls.append(1)
            return 7

    monkeypatch.setattr("connectors.email.service.enabled", _Email.enabled)
    monkeypatch.setattr("connectors.email.service.reseed", _Email.reseed)

    out = await reseed.reseed_all()

    assert calls == [1]
    assert out["email"] == 7


@pytest.mark.anyio
async def test_reseed_all_skips_a_disabled_email_connector(monkeypatch):
    calls = []
    monkeypatch.setattr("connectors.email.service.enabled", lambda: False)
    monkeypatch.setattr("connectors.email.service.reseed", lambda: calls.append(1))

    out = await reseed.reseed_all()

    assert calls == []
    assert "email" not in out


@pytest.mark.anyio
async def test_reseed_all_never_raises_even_if_email_blows_up(monkeypatch):
    """Reset must never fail, or slow down, because a connector's reseed misbehaved."""
    monkeypatch.setattr("connectors.email.service.enabled", lambda: True)

    async def _boom():
        raise RuntimeError("mailbox on fire")

    monkeypatch.setattr("connectors.email.service.reseed", _boom)

    out = await reseed.reseed_all()

    assert "email" not in out
