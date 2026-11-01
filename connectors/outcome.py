"""connectors/outcome.py — every call to an outside provider says what happened (V2-833 F0).

The class this exists for: a provider lookup that failed and returned «nothing» in silence (`except: return "", ""`),
so «I could not ask» and «there is no such thing» reached the turn as the same empty answer — and nobody, not the
engine's visor nor the Master, could tell which. Measured 2026-11-01 on a hosted engine: ten song lookups came back
empty from the in-page player's resolver and no event said why.

One shape for every external call, emitted by the door that makes it, read by both surfaces (kind `provider`):

    provider · op · ok · reason ∈ REASONS · ms · (status / error / any fact the call measured)

`call()` wraps the network call itself: success is `found` (or `empty`, by the caller's own test of the answer), an
exception is `unreachable` with its HTTP status or error type — and is RE-RAISED, so each caller keeps the fallback it
already had. Facts are numbers and codes, never what the user asked for.
"""
from __future__ import annotations

import time

#: The one vocabulary of what a provider call ended in.
FOUND, EMPTY, UNREACHABLE, NOT_CONNECTED, NO_DEVICE = "found", "empty", "unreachable", "not_connected", "no_device"


def report(provider: str, op: str, *, ok: bool, reason: str, ms: int = 0, **facts) -> dict:
    """Emit one outcome. Never raises: a report never takes the call it describes down."""
    out = {"provider": str(provider), "op": str(op), "ok": bool(ok), "reason": str(reason), "ms": int(ms),
           **{k: v for k, v in facts.items() if isinstance(v, (str, int, float, bool)) and v not in ("", None)}}
    try:
        from voice.observer import emit
        emit("provider", f"{'✅' if ok else '⚠️'} {provider} · {op} · {reason}", role="system", extra=out)
    except Exception as e:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).debug("outcome not emitted: %s", e)
    return out


def _status(e: Exception):
    """The HTTP status an exception carries (urllib's `code`, httpx's `response.status_code`), else None."""
    code = getattr(e, "code", None)
    if isinstance(code, int):
        return code
    resp = getattr(e, "response", None)
    return getattr(resp, "status_code", None)


def call(provider: str, op: str, fn, *, empty=None, refused=None, measure=None, **facts):
    """Run `fn()` (the network call) and report it: `found`, `empty` when `empty(result)` is true, `unreachable` on
    an exception — which is re-raised for the caller's own fallback. `measure(result)` adds facts read off the answer
    (its size, how many hits it carried). `refused(result)` true = the provider answered with a refusal (an HTTP 4xx/5xx
    returned rather than raised): reported `unreachable`, the result still handed back."""
    t0 = time.monotonic()
    try:
        out = fn()
    except Exception as e:
        report(provider, op, ok=False, reason=UNREACHABLE, ms=int((time.monotonic() - t0) * 1000),
               error=type(e).__name__, status=_status(e), **facts)
        raise
    is_refused = bool(refused(out)) if refused is not None else False
    is_empty = not is_refused and (bool(empty(out)) if empty is not None else False)
    try:
        facts = {**facts, **(measure(out) if measure is not None else {})}
    except Exception:  # noqa: BLE001 — a fact that cannot be read is left out, the outcome still lands
        facts = dict(facts)
    report(provider, op, ok=not (is_empty or is_refused), reason=UNREACHABLE if is_refused else EMPTY if is_empty else FOUND,
           ms=int((time.monotonic() - t0) * 1000), **facts)
    return out
