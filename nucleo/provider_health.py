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


class CooldownStore:
    """Per-name cooldown expiry, backed by `memory.kv_*` under `kv_name`. Lazy-loaded once per instance."""

    def __init__(self, kv_name: str):
        self._kv = kv_name
        self._cooldown: dict[str, float] = {}
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
                self._cooldown.update({k: float(v) for k, v in saved.items() if float(v) > now})
        except Exception:
            pass

    def _save(self) -> None:
        try:
            from memory import api as memory
            memory.kv_set(self._kv, {k: v for k, v in self._cooldown.items() if v > time.time()})
        except Exception:
            pass

    def available(self, name: str) -> bool:
        self._load()
        return self._cooldown.get(name, 0) <= time.time()

    def until(self, name: str) -> float:
        """Epoch at which `name` becomes available again (0.0 = not in cooldown)."""
        self._load()
        return self._cooldown.get(name, 0)

    def set(self, name: str, until: float) -> None:
        """Extend `name`'s cooldown to `until` — never shortens an existing one (`max`)."""
        self._load()
        self._cooldown[name] = max(self._cooldown.get(name, 0), until)
        self._save()

    def lift(self, name: str) -> None:
        """Clear `name`'s cooldown early (e.g. its relay ran out of turn budget)."""
        self._load()
        if self._cooldown.pop(name, None) is not None:
            self._save()

    def clear(self, name: str = "") -> None:
        """Operator override: forget one cooldown, or all of them."""
        self._load()
        if name:
            self._cooldown.pop(name, None)
        else:
            self._cooldown.clear()
        self._save()


def token_for(tier: dict) -> str:
    """First non-empty env var among `tier['env']` — the credential for that chain step, or "" if unset."""
    for name in tier.get("env") or []:
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return ""
