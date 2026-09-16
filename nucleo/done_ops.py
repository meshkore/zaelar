"""nucleo/done_ops.py — what actually HAPPENED to the operator's data, as a fact of the next turn.

V2-707 F6. Measured in session `080b96a7` (2026-09-16):

    i=10545   agenda:clear_range executed  (4 rows, the 16th)
    i=10780   agenda:clear_range executed  (5 rows, the 17th)
    i=10817   «I haven't deleted anything — no deletion was confirmed in this conversation.»
    i=10853   «In this conversation I never confirmed a deletion, so nothing has been removed from your
               calendar — the three all-day entries on the 17th are still there.»

Both sentences are the model reasoning about the CONFIRMATION LEDGER, which is the only thing it had:
`widgets/confirm.pending_line()` says what is WAITING for a yes, and the window carries what was SAID.
Nothing anywhere told the turn what the engine had DONE. So it deduced from the absence of a pending
confirmation that nothing happened — and told its owner his calendar was intact while it was two sweeps
lighter. He spent six turns trying to convince it otherwise.

## Why here and not in the window

The window holds the conversation, and a mutation is not a sentence: it happens in a detached task after
the turn has already spoken, often in a LATER turn than the one that proposed it (that is the whole shape
of the confirm gate — propose now, execute on «yes»). `brain._last_dataop` exists but is a single slot
owned by the anti-drag guard, deliberately overwritten and deliberately private to it.

So this is a small ring of FACTS, written at the one funnel every mutation crosses
(`widgets/server_api._dispatch`) and only when the call came back without a refusal — the same rule
V2-707 F0 put on the anti-drag seal: an action the door REFUSED is not something that happened.

It is a rail on CONSEQUENCE in the plainest sense: it constrains nothing and forbids nothing. It reports.
"""
from __future__ import annotations

import time

#: Ring of what happened, newest last. Small on purpose: this answers «what did you just do to my data»,
#: not «what has this installation ever done» — that is observability's job, and it has the events table.
_DONE: list[dict] = []
_MAX = 40
#: How far back a mutation is still part of the CONVERSATION. Beyond this the operator is not asking about
#: this turn any more, and the prompt should not carry it.
WINDOW_S = 1800.0


def note(wid: str, action: str, payload: dict | None = None, *, n: int | None = None,
         destructive: bool | None = None) -> None:
    """Record one mutation that ACTUALLY ran. Never raises: it is called from inside the widget funnel."""
    try:
        wid, action = str(wid or "").strip().lower(), str(action or "").strip()
        if not wid or not action:
            return
        _DONE.append({"wid": wid, "action": action, "at": time.time(), "n": n,
                      "destructive": bool(destructive),
                      "payload": {k: v for k, v in (payload or {}).items()
                                  if isinstance(v, (str, int, float, bool))}})
        del _DONE[:-_MAX]
    except Exception:  # noqa: BLE001
        pass


def recent(within_s: float = WINDOW_S, limit: int = 8) -> list[dict]:
    """The mutations of the last `within_s` seconds, newest last, at most `limit`."""
    cut = time.time() - float(within_s)
    return [d for d in _DONE if float(d.get("at") or 0) >= cut][-int(limit):]


def destructive_since(within_s: float = WINDOW_S) -> list[dict]:
    """Only the ones that took something away — the class the operator's question is always about."""
    return [d for d in recent(within_s, limit=_MAX) if d.get("destructive")]


def reset() -> None:
    """Clear the ring. For tests, and for a session boundary that wants a clean slate."""
    _DONE.clear()
