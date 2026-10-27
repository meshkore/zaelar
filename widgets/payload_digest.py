"""What a widget action CARRIED, for the trace: scalars only, clipped, never a field whose name says secret.

Moved out of `widgets/server_api.py` (refactor2710-01, file-size ratchet); the server re-exports it.
"""
from __future__ import annotations

_SECRET_KEY_RE = __import__("re").compile(r"pass|secret|token|key|auth|cred|cookie|session|otp|pin", __import__("re").I)


def _payload_digest(payload) -> dict:
    """What an action CARRIED, for the trace — scalars only, clipped, and never a field whose name says secret.

    Demo pass 30 (2026-09-28, V6): the player reported `player_error` and the trace kept only the action's
    NAME — not the code (101/150 = embedding refused by the owner) nor which video, so a correct fallback and
    a broken player read the same from outside. The widget sends both; the event now keeps them."""
    out: dict = {}
    if not isinstance(payload, dict):
        return out
    for k, v in list(payload.items())[:12]:
        if _SECRET_KEY_RE.search(str(k)):
            continue
        if isinstance(v, (str, int, float, bool)) or v is None:
            out[str(k)[:40]] = v if not isinstance(v, str) else v[:120]
        elif isinstance(v, (list, tuple)):
            out[str(k)[:40]] = f"[{len(v)}]"
    return out
