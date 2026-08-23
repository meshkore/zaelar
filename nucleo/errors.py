"""One short line out of an exception — the idiom that was copied fifteen times and crashed on the empty case.

Reported by the harness on 2026-08-23 with the run it killed: `cheapest-monitor` died on turn 10 with an HTTP
500, and the engine log carried `IndexError: list index out of range` from

    _err = str(e).splitlines()[0][:200]

`"".splitlines()` is `[]`, so ANY exception without a message —`TimeoutError()`, `CancelledError()`, a bare
`RuntimeError('')`— makes the line itself raise. Verified on all three before writing this.

WHERE it sat is what turns a small bug into a bad one: every one of the fifteen copies is inside an `except`
handler, and the one in `probe.py` is the handler that classifies a provider failure and decides the chain
RELAY. So a provider dying silently took the failure handler down with it — the turn returned 500 and **the
relay never happened**. The safety net tore exactly when it was needed, and the symptom named the wrong thing.

Not a formatting nicety, then: an error path that can raise has no error path. Hence one function, imported —
fifteen copies of a line is fifteen chances to fix fourteen.

Pure stdlib and zero imports on purpose: it has to be reachable from `widgets/`, `nucleo/` and `voice/` alike
without creating a cycle or a new dependency direction.
"""
from __future__ import annotations


def brief(exc: object, limit: int = 200) -> str:
    """The first line of `exc`, capped — and `""` when there is nothing to say, never an exception of its own.

    The empty answer is deliberate and safe here: every caller is already inside an `except`, building a message
    for a log or a UI field, and an empty detail there degrades a message. A raise LOSES the handler."""
    try:
        text = str(exc)
    except Exception:            # a __str__ that itself raises is rare and real (wrapped C errors do it)
        return exc.__class__.__name__ if hasattr(exc, "__class__") else ""
    lines = text.splitlines()
    if not lines:
        # No message at all: name the TYPE instead of returning nothing. «TimeoutError» in a log beats a blank,
        # which is what the original crash was trying to avoid producing in the first place.
        return (exc.__class__.__name__ if hasattr(exc, "__class__") else "")[:limit]
    return lines[0][:limit]
