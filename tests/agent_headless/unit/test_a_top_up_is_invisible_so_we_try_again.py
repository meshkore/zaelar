"""Six hours mute, with a healthy provider standing next to it, because a top-up cannot be seen from here.

Measured 2026-08-27. At 18:55 DeepSeek answered `402 Insufficient Balance`, so both direct rungs were punished
for six hours and the chain moved to the broker. The operator topped up at ~19:40. Nothing changed: a balance
is not a quota, there is no reset date to wait for, and the engine has no way to learn that money arrived. At
22:07 the broker itself started timing out — and the brain went silent with a provider that had been healthy
for two and a half hours one rung above it. The engine's own warning said «it does not come back on its own; it has to be recharged»;
the operator HAD recharged, and there was no way to tell it so.

The old ceiling was right about the world and wrong about us: a balance really does not refill by itself, but
the alert exists precisely to make someone refill it, so the interesting moment is always right after. The
only way to notice a top-up is to try again. Parole costs ~3 failed calls an hour while the account is truly
dry; not having it cost six hours of silence.

Both chains carry their own copy of the constant, on purpose (`provider_chain` for the brains, `providers`
for the CLI rungs — a model tier being down says nothing about a CLI endpoint being down). Duplicated state,
one rule: these tests hold the rule over both copies, so a change to one that forgets the other is red.
"""
from __future__ import annotations

import time

import pytest

from nucleo.flash import provider_chain as PC
from nucleo.workers import providers as WP

_CHAINS = pytest.mark.parametrize("mod", [PC, WP], ids=["cerebros", "workers"])


@_CHAINS
def test_a_dry_balance_gets_parole_not_a_sentence(mod):
    """The window has to be short enough that a top-up is noticed while the person still remembers making it."""
    assert mod._DEPLETED_COOLDOWN_S <= 30 * 60, (
        "a dry rung is punished for longer than half an hour: a top-up made right after the alert would not be "
        "picked up, which is the failure this exists to prevent")


@_CHAINS
def test_but_it_is_still_a_punishment(mod):
    """Sensitivity in the other direction: no cooldown at all means relaying to yourself and failing in a
    loop, which is what these modules were built to stop."""
    assert mod._DEPLETED_COOLDOWN_S >= 5 * 60, "the rung is barely punished — this reopens the retry loop"


@_CHAINS
def test_a_quota_still_waits_for_its_own_reset_date(mod):
    """The distinction that must not blur: a QUOTA says «wait until X» and we believe it; a BALANCE has no
    date to wait for. Parole belongs to the second, and shortening it must not shorten the first."""
    assert mod._DEFAULT_COOLDOWN_S >= 30 * 60


def test_the_dry_rung_really_gets_the_short_window(monkeypatch):
    """The half that matters in production: the constant is only worth anything if it is what gets stored."""
    seen = {}
    monkeypatch.setattr(PC._store, "set", lambda name, until, reason=None: seen.update(name=name, until=until))
    monkeypatch.setattr(PC, "pick", lambda role=None: {"name": "titular", "base_url": "https://x", "plan": ""})
    PC.note_failure('{"error":{"message":"Insufficient Balance"}}', role=PC.ROLE_VOICE)
    assert seen, "a dry balance did not punish anything"
    left = seen["until"] - time.time()
    assert left <= 30 * 60 + 5, f"the dry rung was sentenced for {left/60:.0f} min, not paroled"
