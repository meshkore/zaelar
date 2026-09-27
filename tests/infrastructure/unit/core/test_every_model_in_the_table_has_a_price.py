"""Every model the model table names has a PRICE OF ITS OWN (V2-767).

`test_energy_coverage.py` guards the other half of this: that nobody spends outside the meter. This one
guards the half that failed on 2026-09-25 — spending INSIDE the meter at a price nobody chose.

What happened, measured: `config/models.default.json` names `deepseek-flash` as titular of voice_brain,
memory_writer, memory_rem, triage and susurro — the hottest path in the product. `energy_meter._MODEL_RATES`
only knew the older broker name `deepseek-v4-flash`, and the lookup is a SUBSTRING match, so the new name
matched nothing and every voice turn on a cloud account billed at the punitive catch-all (1.00, 5.00): 3.3x
input and 4.2x output of its real price. Nothing failed and nothing was logged as an error — the meter
reported success, the customer's Energy just drained faster.

The same day, and from the same cause, `deepseek-v4-pro` carried (0.28, 0.42) against a real (1.32, 3.96):
under-metering by 4.7x, which is the expensive direction. Its correct row was ALSO already present higher up
in the literal and was dead: a repeated key in a dict literal keeps the LAST value.

So a price cannot be left to a substring coincidence. Renaming a model in the table is a one-line edit that
changes what a customer is billed, and this is what makes that edit say so out loud.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from nucleo import energy_meter

ENGINE = Path(__file__).resolve().parents[4]
TABLE = ENGINE / "config" / "models.default.json"

#: Providers that bill no tokens: nothing to price.
_NO_TOKENS = {"off", "", None}


def _rungs() -> list[tuple[str, str, dict]]:
    """(service, rung, rung-dict) for every rung that reaches a paid endpoint."""
    services = json.loads(TABLE.read_text(encoding="utf-8"))["services"]
    out = []
    for name, svc in services.items():
        for kind in ("titular", "failover"):
            rung = svc.get(kind)
            if not rung or rung.get("provider") in _NO_TOKENS:
                continue
            # STT/TTS are priced per minute / per 1k characters in the TARIFF table (authored in the
            # master, `nucleo/energy_tariffs.py`), not per token — they carry no model name here.
            if not rung.get("model"):
                continue
            out.append((name, kind, rung))
    return out


@pytest.mark.parametrize("service,kind,rung", _rungs(), ids=lambda v: v if isinstance(v, str) else "")
def test_the_model_has_an_explicit_rate(service, kind, rung):
    model = rung["model"]
    rate = energy_meter._rate_for(rung.get("base_url", ""), model)
    assert rate != energy_meter._FALLBACK_RATE_USD, (
        f"{service}.{kind} names «{model}» and the meter has NO row for it, so it bills at the punitive "
        f"catch-all {energy_meter._FALLBACK_RATE_USD} $/1M. Add its real price (from the provider's own "
        f"pricing page, never from memory) to `_MODEL_RATES` in nucleo/energy_meter.py."
    )


def test_no_rate_is_written_twice():
    """A repeated key in the literal keeps the LAST value and silently voids the first — which is exactly
    how `deepseek-v4-pro` kept a stale price while its corrected row sat right there, unread."""
    source = (ENGINE / "nucleo" / "energy_meter.py").read_text(encoding="utf-8")
    for table in ("_MODEL_RATES", "_RATES_PER_1M_TOKENS_USD", "_CACHED_READ_RATES_USD"):
        start = source.index(f"{table}:")
        body = source[start:source.index("\n}", start)]
        keys = [line.split('"')[1] for line in body.splitlines()
                if line.strip().startswith('"') and '":' in line]
        dupes = {k for k in keys if keys.count(k) > 1}
        assert not dupes, f"{table} names {sorted(dupes)} more than once: only the last one counts."


def test_a_cached_read_is_never_dearer_than_fresh_input():
    """A cache hit is a DISCOUNT. If a row ever prices it above fresh input the meter is not merely
    imprecise, it is upside down — and the hit is the counter that grows most in a long session."""
    for model, cached in energy_meter._CACHED_READ_RATES_USD.items():
        fresh_in, _ = energy_meter._rate_for("", model)
        assert cached <= fresh_in, (
            f"«{model}»: cached read ${cached}/1M is dearer than fresh input ${fresh_in}/1M."
        )
