"""nucleo/flash/repair_grounding.py — a call the REPAIR pass writes may only carry what somebody actually said.

`act_repair` asks the model, once more and with no operator in the loop, for the call it should have made. That pass
fills the payload on its own, so its free values are the ones nobody checked. Two measured inventions:

  · V2-781: «avísame cuando esté» became `send_to {"contact": "zaelar"}` — the assistant's own name as recipient.
  · `build-a-video-playlist-from-links` (2026-10-10): «Dale, ¿y qué está sonando ahora?» became
    `musica:play_playlist {"playlist": "Favoritos"}`. Nobody had said «Favoritos»; it is the music card's DEFAULT
    list name (its manifest describes `favorite_current` with it), and the card held no list at all. The turn
    answered «No encuentro ninguna lista que se llame «Favoritos»» to a man whose list was «la de la tarde».

Both are the same bound: a value that SELECTS something (who receives a message, which named list to act on) must
be in his words, in the conversation, or on the card the call is about. A value the pass composes (a note's text, a
new title) is not checked here — it is written, not selected.
"""
from __future__ import annotations

import unicodedata

#: Payload keys that name an EXISTING list to act on. Not `name`: a `create_*{name}` is a new name he may dictate in
#: other words, and `name` is a person or a title elsewhere.
LIST_REFERENCE_KEYS = ("playlist", "list", "list_name")


def _fold(text: str) -> str:
    s = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.replace("«", " ").replace("»", " ").replace("'", " ").replace('"', " ").split())


def _heard(operator_text: str, window) -> str:
    return " ".join([operator_text or ""] + [str((m or {}).get("content") or "") for m in (window or [])
                                             if isinstance(m, dict) and m.get("role") == "user"])


def recipient_was_named(wid: str, action: str, payload: dict, operator_text: str, window) -> bool:
    """An outbound message a repair invents must go to someone his words or the conversation carry."""
    try:
        from widgets import effects as _fx
        if not _fx.carries(wid, action, _fx.EXTERNAL_SEND):
            return True
        who = str(payload.get("contact") or payload.get("to") or "").strip().lower()
        return not who or who in _heard(operator_text, window).lower()
    except Exception:  # noqa: BLE001
        return True


def list_was_named(payload: dict, operator_text: str, window, card_digest: str = "") -> bool:
    """A named list the repair selects must be one he said, or one the card holds. Never raises (True = allow)."""
    try:
        heard = _fold(_heard(operator_text, window) + " " + (card_digest or ""))
        for key in LIST_REFERENCE_KEYS:
            val = _fold((payload or {}).get(key) or "")
            if val and val not in heard:
                return False
        return True
    except Exception:  # noqa: BLE001
        return True
