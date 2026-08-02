"""
i18n.init — the INITIALIZATION side of the multilingual subsystem (V2-089).

Everything here PREPARES a language: it may call an LLM (generate) or run detection (P3), can take a few seconds,
and runs only at boot / first-run / language-switch / upgrade — behind the 'preparing language' veil. It is
strictly separated from i18n.runtime (the hot path that just serves already-prepared bundles).

`prepare(code)` is THE single idempotent entry the boot sequence and the language-switch path call.
"""
from __future__ import annotations

from i18n.init.ensure import ensure_language


async def prepare(code: str) -> dict:
    """Make the active language ready: generate/top-up its bundle if any manifest key is missing or changed.
    Idempotent — a cheap no-op for presets and already-current languages. Returns {code, generated, total, …}."""
    return await ensure_language(code)


__all__ = ["prepare", "ensure_language"]
