"""search/providers/keys.py — which provider has a key, by NAME (V2-782 T2.1).

Values never leave this module except to the HTTP header of the provider they belong to. Everything that
reports — the health probe, the panel line, a test — asks `present()` / `key_name()` and gets names.
"""
from __future__ import annotations

import os

from . import PROVIDERS


def spendable() -> bool:
    """May a PAID index be asked right now? The energy lease's answer (always yes when no lease is configured)."""
    from nucleo.energy import lease as energy_lease
    return energy_lease.check("search")


def leased() -> bool:
    """Is this deployment's spending bounded by an energy lease? Then a probe nobody asked for is not paid for."""
    from nucleo.energy import lease as energy_lease
    return energy_lease.enabled()


def key(provider: str) -> str:
    """The key VALUE for `provider` — for the provider module's own HTTP call, nothing else.

    THE LEASE GATE for paid search. Every paid index reads its key here immediately before its request, so a
    machine with no usable energy lease gets no key: the chain skips the paid rungs exactly as it skips an
    unkeyed one and degrades to the free ones, the probe says `unfunded`, and nothing is spent."""
    if PROVIDERS[provider].paid and not spendable():
        return ""
    for name in PROVIDERS[provider].keys:
        v = (os.getenv(name) or "").strip()
        if v:
            return v
    return ""


def key_name(provider: str) -> str:
    """The env var that holds (or would hold) the key. Names are what reports and docs say."""
    p = PROVIDERS[provider]
    for name in p.keys:
        if (os.getenv(name) or "").strip():
            return name
    return p.keys[0] if p.keys else ""


def present(provider: str) -> bool:
    """A keyless provider is always present unless its env switch turns it off."""
    p = PROVIDERS[provider]
    if p.env_switch[0] and (os.getenv(p.env_switch[0]) or "") == p.env_switch[1]:
        return False
    return bool(key(provider)) if p.keys else True
