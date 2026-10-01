"""The messaging card's timing and view freshness: «escribiendo…», the mail signature, a pushed view's TTL (V2-778 F1).

Moved out of `widgets/mensajeria/data.py` (over the 900 lines a new file may reach): how long the card shows that a
message is being composed, the signature line it previews, and how long a pushed view stays worth obeying.
Unchanged; `data` imports every name back.
"""
from __future__ import annotations

import time


# ── The VIEW is a declared ACTION (V2-543 — the V2-540/V2-541 lesson applied here) ──────────────────────────────
# The platform lens used to be widget.js-local state the voice could not touch, and "back to the main list" had no
# action at all: measured live (2026-09-01 18:39), «ve a la lista principal de los mensajes» could only re-show the
# widget, which changes nothing. The requested view is pushed with a MONOTONIC witness counter (`n`) so asking for
# the same view twice still lands (the token moves even when the value repeats), and it EXPIRES server-side: a
# pushed lens kept forever would yank next week's reopen back to a stale filter.
_VIEW_TTL_S = 600


def _push_view(db: dict, platform: str) -> None:
    prev = db.get("view") or {}
    db["view"] = {"platform": platform, "n": int(prev.get("n", 0) or 0) + 1, "at": time.time()}


def _fresh_view(db: dict):
    """The pushed view, or None once it has expired. Expiry costs an open widget nothing: `view` merely stops
    arriving, the client token stops moving, and whatever the operator chose by hand survives."""
    v = db.get("view")
    if not isinstance(v, dict):
        return None
    try:
        if time.time() - float(v.get("at", 0) or 0) > _VIEW_TTL_S:
            return None
    except (TypeError, ValueError):
        return None
    return v


# SEEN BEING SENT (operator's demo note, 2026-09-28): «que se vea cómo se lo mandamos y cómo se le da el botón» —
# a voice-ordered message went out in the background and, without sound, nobody watching could tell anything had
# been sent. `send_to` now opens that conversation, and the order waits in the queue for as long as typing the
# text takes; the card types it and presses its own send button at the moment the order is released. The send
# itself is the same queued order either way: with the card closed it simply leaves a few seconds later.
_COMPOSE_BASE_S = 1.2


_COMPOSE_PER_CHAR_S = 0.03


_COMPOSE_MAX_S = 7.0


_COMPOSE_LINGER_S = 4.0


def _compose_seconds(text: str) -> float:
    return min(_COMPOSE_MAX_S, _COMPOSE_BASE_S + _COMPOSE_PER_CHAR_S * len(str(text or "")))


def _composing(db: dict) -> dict | None:
    c = db.get("composing")
    now = time.time()
    if not isinstance(c, dict) or now > float(c.get("send_at") or 0) + _COMPOSE_LINGER_S:
        return None
    # Relative times, so the card re-anchors them on ITS clock: a browser a few seconds off would otherwise
    # press the button before (or after) the order actually leaves.
    return {**c, "elapsed_s": round(now - float(c.get("started") or now), 2),
            "left_s": round(max(0.0, float(c.get("send_at") or 0) - now), 2)}


def _email_signature() -> list:
    try:
        from connectors.email import config as _email_cfg
        return _email_cfg.signature_lines()
    except Exception:
        return []
