"""search/providers/keys.py — which provider has a key, by NAME (V2-782 T2.1).

Values never leave this module except to the HTTP header of the provider they belong to. Everything that
reports — the health probe, the panel line, a test — asks `present()` / `key_name()` and gets names.
"""
from __future__ import annotations

import os

from . import PROVIDERS


def key(provider: str) -> str:
    """The key VALUE for `provider` — for the provider module's own HTTP call, nothing else."""
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
