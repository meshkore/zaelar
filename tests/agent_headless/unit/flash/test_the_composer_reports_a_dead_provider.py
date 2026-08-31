"""V2-225 — the composer READ the provider chain and never WROTE to it.

`research._spec()` goes through `provider_chain.pick()` and its docstring promises that «if the primary provider is
out of quota, it relays instead of dying». The promise was not fulfilled, and not because the relay was missing:
`note_failure()` had only ONE production caller in the entire tree —`connectors/meshkore/brain.py`, the cluster
brain—, so the cooldown that triggers the relay existed only if the CLUSTER had previously failed at the same
point. The composer relied on that coincidence.

Measured by the harness in two rounds of `hotel-under-15-days` (2026-08-20): at 20:01, 20:07, and 20:10, the
SAME exhausted provider was selected all three times, with two FastClient retries each time, and the worker came
out blind after each one —

    research: the composer failed (429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at
    2026-08-25 01:39:02]) — the worker exits WITHOUT a brief (unguided search)

That text is exactly the form that `classify_failure` reads as `exhausted` WITH a reset date, which is the case
that sets a cooldown and returns a relay. The mechanism was not missing: the call was missing. Until 2026-08-25,
that meant EVERY research escalation came out unguided — which is why the best «result» of one round was a €25
flamenco show.
"""
import asyncio

import pytest

from nucleo import research

EXHAUSTED = "429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2027-01-01 01:39:02]"
LEAD = {"name": "zai", "base_url": "https://api.z.ai/v1", "model": "glm", "api_key": "k"}
RELAY = {"name": "deepseek", "base_url": "https://api.deepseek.com", "model": "v4", "api_key": "k"}


class _Spy:
    def __init__(self, relay=RELAY):
        self.relay, self.reported, self.used = relay, [], []

    def note_failure(self, text, tier=None, **kw):
        self.reported.append((text, tier))
        return self.relay


@pytest.fixture
def wired(monkeypatch):
    """The chain and client are mocked; what is verified is the contract between them.

    `ZAELAR_RESEARCH` is set manually because this machine's environment sets it to `0`, and with the composer off
    `compose()` exits on the first line without touching anything: all seven tests would pass along the wrong path."""
    monkeypatch.setenv("ZAELAR_RESEARCH", "1")
    spy = _Spy()
    from nucleo.flash import provider_chain as pc
    monkeypatch.setattr(pc, "pick", lambda *a, **k: LEAD)
    monkeypatch.setattr(pc, "spec_for", lambda t: t)
    monkeypatch.setattr(pc, "note_failure", spy.note_failure)

    class _Client:
        async def complete(self, msgs, spec=None, **kw):
            spy.used.append((spec or {}).get("name"))
            if (spec or {}).get("name") == LEAD["name"]:
                raise RuntimeError(EXHAUSTED)
            return '{"research": false}'

    monkeypatch.setattr("nucleo.flash.fast_client.FastClient", lambda *a, **k: _Client())
    return spy


def test_the_dead_provider_is_REPORTED_to_the_chain(wired):
    asyncio.run(research.compose("búscame un hotel de 4 estrellas en Sevilla"))
    assert wired.reported, "nadie le dijo a la cadena que ese escalón está agotado: el relevo no puede dispararse"
    assert wired.reported[0][1] == LEAD


def test_and_the_message_that_travels_is_the_one_the_chain_knows_how_to_read(wired):
    """`classify_failure` distinguishes a bare 429 (retry on its own) from an exhausted-quota one WITH a reset date
    (relays and sets a cooldown until the reset). Sending anything else is not reporting."""
    asyncio.run(research.compose("hotel en Sevilla"))
    assert "Limit Exhausted" in wired.reported[0][0]


def test_THIS_task_is_saved_too_not_only_the_next_one(wired):
    """The evidence is three consecutive tasks running blind. Marking the tier fixes the next one; retrying with the
    relay also fixes the one currently in progress."""
    asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.used == [LEAD["name"], RELAY["name"]]


def test_with_NO_relay_the_fail_open_is_untouched(monkeypatch, wired):
    """The fail-open behavior is correct and remains untouched: without a relay, the worker exits without a brief,
    as always. The only thing added is the line that marks the provider before giving up."""
    wired.relay = None
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.reported


def test_a_relay_that_is_the_SAME_tier_is_not_a_relay(monkeypatch, wired):
    """Sensitivity, and the loop that this module exists to break: retrying against the tier that just failed is
    spending the budget twice for the same 429."""
    wired.relay = LEAD
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.used == [LEAD["name"]]


def test_a_model_PINNED_by_the_operator_is_never_reported(monkeypatch, wired):
    """`config §research.model` is not a choice made by the chain. Putting a tier that the composer did not use on
    cooldown would relay the cluster brain because of someone else's fault."""
    monkeypatch.setattr("config.v2.get", lambda k, *a: ({"model": "mio", "base_url": "http://x"} if k == "research"
                                                        else {}), raising=False)
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.reported == []


def test_a_timeout_is_not_a_dead_provider(wired, monkeypatch):
    """Sensitivity in the other direction: a slow composer is not an out-of-quota provider, and putting it on
    cooldown would shut down a healthy tier. The `except TimeoutError` still comes first and does not pass through here."""
    async def _slow(*a, **k):
        raise asyncio.TimeoutError()
    monkeypatch.setattr("nucleo.flash.fast_client.FastClient",
                        lambda *a, **k: type("C", (), {"complete": staticmethod(_slow)})())
    with pytest.raises(research.ComposerUnavailable):
        asyncio.run(research.compose("hotel en Sevilla"))
    assert wired.reported == []
