"""nucleo/actionmap — a KNOWN phrase skips the model (V2-539).

Pre-LLM exact match of one finalized utterance (a short phrase bounded by silence) against a per-language
table of verified command phrases. A hit executes the mapped direct action in SILENCE through the same
dispatch funnels the FlashBrain uses, in <1 ms instead of a full model turn. Everything that is not a
verbatim hit — longer phrasing, a compound sentence, a negation, novelty — falls through untouched:
**when in doubt, the model.** The map never splits an utterance and never classifies intent (V2-095
doctrine); its certainty comes from the provenance of the entry, not from string similarity.

Wired in BOTH channels (voice `nucleo.py::_run_inner` and text `probe.py::run_turn` — the parallel-impl
rule) through this one module. Kill switches: env ZAELAR_ACTIONMAP=0 (checked first, off-only) and
config `actionmap.enabled` (the Susurro template). Every path fails open to the model.
"""
from __future__ import annotations

import os

from . import executor as _executor
from . import store as _store
from .normalize import normalize

__all__ = ["enabled", "match", "execute", "describe", "record_hit", "invalidate"]


def enabled() -> bool:
    """Env first and OFF-ONLY (a broken config store must not be able to force the module on), then config.
    Known precedence trap documented in config/v2.py: a stored value beats the env fallback — which is why
    the env check here is explicit and first."""
    if (os.getenv("ZAELAR_ACTIONMAP", "1") or "1").strip().lower() in ("0", "false", "no", "off"):
        return False
    try:
        from config import v2 as _v2
        return bool(_v2.get("actionmap").get("enabled", True))
    except Exception:
        return True


def match(text: str) -> dict | None:
    """The whole normalized utterance against the active language's index. Returns the entry
    ({id, action, source, phrase}) or None. One dict lookup; never raises.

    Guard (belt and braces — an exact match on a non-negated seed phrase can't normally trip this): a hit
    whose utterance reads as a NEGATED clause is refused, so a bad learned entry containing a negation can
    never fire the affirmative action."""
    phrase = normalize(text)
    if not phrase:
        return None
    entry = _store.index().get(phrase)
    if entry is None:
        return None
    try:
        from nucleo.flash.negation import clause_negated
        if clause_negated(phrase, 0, len(phrase)):
            return None
    except Exception:
        pass
    return dict(entry, phrase=phrase)


def execute(entry: dict, emit, phrase: str = "") -> bool:
    """Run a matched entry's action. True = executed (caller ends the turn); False = could not execute
    with certainty (caller falls through to the model — a routing decision, not an error)."""
    ok = _executor.execute(entry.get("action") or {}, emit, phrase=phrase)
    if ok:
        _store.record_hit(int(entry.get("id") or 0))
    return ok


def describe(entry: dict) -> str:
    return _executor.describe(entry.get("action") or {})


def record_hit(entry_id: int) -> None:
    _store.record_hit(entry_id)


def invalidate() -> None:
    _store.invalidate()
