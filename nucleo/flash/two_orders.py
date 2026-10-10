"""nucleo/flash/two_orders.py — two payload-less actions on one card are two ORDERS when the turn's verdict read both.

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-10 19:50): «súbele un poco el volumen que lo tengo
silenciado. Y ya pásate al siguiente.» The model emitted exactly the two right calls — `youtube:unmute {}` and
`youtube:next {}` — and only the first ran: `data_ops.admite_data_op` drops a second, different action on the same
card unless both name distinct targets, because that is how the ENUMERATION looks («show me the agenda» →
done/drop/snooze). Controls name nothing, so they can never prove they are two orders by their payload. The reply
said «Te paso al siguiente» over a `next` that never ran.

The proof was already paid for: the turn brief's `screen_action` question reads his words against every declared
action of the open cards, and its distribution gave `youtube:next` 0.28 and `youtube:unmute` 0.20 (volume_up 0.52).
An enumeration is the MODEL listing alternatives his words did not ask for, so the verdict gives them no mass. Two
calls the verdict independently heard in his sentence are his two orders. Nothing here reads his words.
"""
from __future__ import annotations

#: The share of the `screen_action` distribution each action needs to count as heard in his sentence. The measured
#: pair sat at 0.28 and 0.20; an action his words do not touch reads ~0.0.
HEARD_FLOOR = 0.15


def _mass(brief, wid: str, action: str) -> float:
    from nucleo import jev as _jev
    from nucleo.flash import turn_brief as _tb
    verdict = _jev.peek(brief) if isinstance(brief, dict) else None
    ans = (verdict or {}).get(_tb.TARGET_KEY) or {}
    probs = ans.get("probabilities") or ans.get("probs") or {}
    base = str(wid or "").split("::", 1)[0].strip().lower()
    return float(probs.get(f"{base}:{action}") or 0.0)


def both_heard(brief, wid: str, action: str, other: str) -> bool:
    """Did the verdict hear BOTH actions on this card in his sentence? False when it cannot say. Never raises."""
    try:
        if not brief or not action or not other or action == other:
            return False
        return _mass(brief, wid, action) >= HEARD_FLOOR and _mass(brief, wid, other) >= HEARD_FLOOR
    except Exception:  # noqa: BLE001 — unreadable verdict = today's rule (the enumeration guard holds)
        return False
