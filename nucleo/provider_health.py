"""nucleo/provider_health.py — shared cooldown/circuit-breaker mechanics for provider chains (V2-098).

`nucleo/flash/provider_chain.py` (model tiers for the FlashBrain/cluster brain) and `nucleo/workers/providers.py`
(Anthropic-compatible endpoints for the Claude Code CLI) independently reinvented the identical cooldown
bookkeeping — load/save to `memory.kv_*`, per-name expiry, env-var token lookup — down to matching variable
names (`_cooldown`/`_load`/`_save`/`_token_for`/`_available`). They deliberately do NOT share cooldown STATE
(different KV namespaces: a model tier being down says nothing about a worker CLI endpoint being down) — only
the MECHANICS, which is what this module factors out.
"""
from __future__ import annotations

import os
import time


#: A cooldown because the provider is BROKEN (no quota, no balance, bad credential). Time is the only cure,
#: and no amount of latency bookkeeping can shorten it.
REASON_HEALTH = "health"
#: A cooldown because the provider was SLOW or stalled. It is perfectly able to answer — we chose to go
#: elsewhere — so a relay running out of turn budget may hand the turn back.
REASON_LATENCY = "latency"


class CooldownStore:
    """Per-name cooldown expiry AND ITS REASON, backed by `memory.kv_*` under `kv_name`.

    The reason is not bookkeeping: measured on `search-secondhand-monitor__es` (2026-08-24 00:56), the same
    process put `z.ai` on cooldown until 2026-08-25 01:39 for having no weekly quota left, and 260 seconds
    later `provider_chain.pick()` lifted it — because the LATENCY relay had run out of turn budget and its
    ceiling calls `lift()` unconditionally. Its own comment says «devuélvele el turno al titular aunque siga
    lento», so the intent was always latency-only; nothing in the store could express that, so it handed the
    next turn to a provider we already knew would answer 429.

    Two mechanisms in one module writing one number and reading it as if it meant one thing. Same shape as
    V2-252's trap by the other side: there a cooldown landed on a HEALTHY provider, here it was cleared off
    a BROKEN one.
    """

    def __init__(self, kv_name: str):
        self._kv = kv_name
        self._cooldown: dict[str, float] = {}
        self._why: dict[str, str] = {}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            from memory import api as memory
            saved = memory.kv_get(self._kv) or {}
            if isinstance(saved, dict):
                now = time.time()
                for k, v in saved.items():
                    # Backwards compatible on purpose: what is on disk RIGHT NOW is `{name: epoch}`, and a
                    # cooldown that fails to load is a provider we go back to hammering. An entry with no
                    # recorded reason is read as HEALTH — the conservative side, since treating an unknown
                    # cooldown as latency is exactly what would let the ceiling lift a quota block.
                    try:
                        until, why = (float(v[0]), str(v[1])) if isinstance(v, (list, tuple)) and len(v) == 2 \
                            else (float(v), REASON_HEALTH)
                    except Exception:
                        continue
                    if until > now:
                        self._cooldown[k] = until
                        self._why[k] = why or REASON_HEALTH
        except Exception:
            pass

    def _save(self) -> None:
        try:
            from memory import api as memory
            memory.kv_set(self._kv, {k: [v, self._why.get(k, REASON_HEALTH)]
                                     for k, v in self._cooldown.items() if v > time.time()})
        except Exception:
            pass

    def available(self, name: str) -> bool:
        self._load()
        return self._cooldown.get(name, 0) <= time.time()

    def until(self, name: str) -> float:
        """Epoch at which `name` becomes available again (0.0 = not in cooldown)."""
        self._load()
        return self._cooldown.get(name, 0)

    def why(self, name: str) -> str:
        """Why `name` is in cooldown (`""` = it is not)."""
        self._load()
        return self._why.get(name, "") if self._cooldown.get(name, 0) > time.time() else ""

    def set(self, name: str, until: float, reason: str = REASON_HEALTH) -> None:
        """Extend `name`'s cooldown to `until` — never shortens an existing one (`max`).

        A HEALTH reason always wins over a latency one, whichever arrived last and whichever expiry is
        longer: a provider that is both slow and out of quota is out of quota, and forgetting that is what
        lets the latency ceiling lift it.
        """
        self._load()
        prev = self._cooldown.get(name, 0)
        self._cooldown[name] = max(prev, until)
        if reason == REASON_HEALTH or self._why.get(name) != REASON_HEALTH or prev <= time.time():
            self._why[name] = reason
        self._save()

    def lift(self, name: str, *, only: str = "") -> None:
        """Clear `name`'s cooldown early (e.g. its relay ran out of turn budget).

        `only` scopes it to a reason: the latency ceiling passes `REASON_LATENCY` so it can hand the turn
        back to a titular we merely found slow, and can NEVER hand it back to one we know has no quota.
        """
        self._load()
        if only and self._cooldown.get(name, 0) > time.time() and self._why.get(name) != only:
            return
        if self._cooldown.pop(name, None) is not None:
            self._why.pop(name, None)
            self._save()

    def clear(self, name: str = "") -> None:
        """Operator override: forget one cooldown, or all of them. Deliberately unscoped — the operator
        saying «try it again» is a decision, not a mechanism resolving its own bookkeeping."""
        self._load()
        if name:
            self._cooldown.pop(name, None)
            self._why.pop(name, None)
        else:
            self._cooldown.clear()
            self._why.clear()
        self._save()


def token_for(tier: dict) -> str:
    """First non-empty env var among `tier['env']` — the credential for that chain step, or "" if unset."""
    for name in tier.get("env") or []:
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return ""
