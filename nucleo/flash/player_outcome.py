"""What a play/next op ENDED in on the video player — read from the card after the player had its say.

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-11, turn 5): «Pasa al siguiente» → `youtube:next` returned
ok with Rick Astley loaded, the transport receipt read the card at that instant and appended «Suena ahora «Rick
Astley…»», and 1.0 s and 1.6 s later the embedded player reported `player_error` 150 for Rick and then for the PSY
swap (the owner blocks embedding) — the list ended `blocked_notice: exhausted`, nothing played. The op's `ok` is the
card ACCEPTING the order; whether the video plays is the player's answer, and it arrives through the card's own JS.

`outcome(card)` reads what the card holds now: `playing`, `blocked` (the player refused it: an error on the current
video, a terminal notice, or the current id on the blocklist) or `swapped` (refused and replaced by a playable one).
`settled(card)` waits, while the card is on a screen that can report, for the player's quiet window before
answering — and returns at once on a terminal refusal. Without a screen there is no player to wait for.
"""
from __future__ import annotations

import asyncio
import time

from loguru import logger

#: The player's refusal arrives ~1 s after the load (measured 0.98 s, then 0.65 s more for the swap's own).
QUIET_S = 1.6
_POLL_S = 0.1


def outcome(card: str) -> dict:
    """`{"state": "playing"|"blocked"|"swapped"|"", "title": str, "to": str}` for the video card; `state` "" when
    the card is not one this reads (the caller keeps its own reading) or holds nothing."""
    if str(card or "").split("::", 1)[0].strip().lower() != "youtube":
        return {"state": "", "title": "", "to": ""}
    try:
        from widgets import store as _st
        from widgets.youtube import availability as _av
        db = _st.load("youtube") or {}
        title = str(db.get("title") or "").strip()
        bn = db.get("blocked_notice") if isinstance(db.get("blocked_notice"), dict) else {}
        kind = str(bn.get("kind") or "")
        if kind in ("exhausted", "explicit"):
            return {"state": "blocked", "title": str(bn.get("from") or title), "to": ""}
        vid = str(db.get("videoId") or "")
        if str(db.get("player_error") or "").strip() or (vid and vid in _av.blocked_ids(db)):
            return {"state": "blocked", "title": title, "to": ""}
        if kind == "swapped":
            return {"state": "swapped", "title": str(bn.get("from") or ""), "to": str(bn.get("to") or title)}
        return {"state": "playing" if title else "", "title": title, "to": ""}
    except Exception as e:  # noqa: BLE001
        logger.debug(f"player_outcome: card unread — {e}")
        return {"state": "", "title": "", "to": ""}


def _on_screen(card: str) -> bool:
    try:
        from nucleo.flash import canvas_visibility as _cv
        return _cv.is_open(card)
    except Exception as e:  # noqa: BLE001
        logger.debug(f"player_outcome: canvas unread — {e}")
        return False


async def settled(card: str, *, quiet_s: "float | None" = None, min_wait: float = 0.0) -> dict:
    """`outcome(card)` once the player had its say: a refusal ends the wait, a swap restarts it (the replacement
    can be refused too), and a quiet window with neither means it plays. `min_wait` lets an op that may still be in
    flight (the voice rail dispatches detached) land before the card is read."""
    quiet_s = QUIET_S if quiet_s is None else quiet_s
    if min_wait > 0:
        await asyncio.sleep(min_wait)
    out = outcome(card)
    if out["state"] in ("", "blocked") or not _on_screen(card):
        return out
    deadline = time.monotonic() + quiet_s
    seen, refused = out, []
    while time.monotonic() < deadline:
        await asyncio.sleep(_POLL_S)
        out = outcome(card)
        if out["state"] == "swapped" and out["title"] and out["title"] not in refused:
            refused.append(out["title"])          # Rick refused, PSY put in his place: both are named at the end
        if out["state"] == "blocked":
            break
        if out != seen:
            seen, deadline = out, time.monotonic() + quiet_s
    if out["state"] == "blocked" and out["title"] and out["title"] not in refused:
        refused.append(out["title"])
    return {**out, "refused": refused or ([out["title"]] if out["state"] == "blocked" and out["title"] else [])}
