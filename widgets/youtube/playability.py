"""widgets/youtube/playability.py — a video the player REFUSED is still in his list, and says so.

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-11): both pasted videos came back `player_error` 150 (the
owner blocks embedding). The blocklist knew it, but the list digest marked only the CURRENT row, so the refused
first video read as a plain item; and `next` past the last (refused) one answered «No hay más vídeos en la lista»,
which the model turned into «Gangnam Style ya no está en la lista» while the card still held both. Two facts are kept
apart here: «there is nothing after this one» and «the next one is here but cannot play on this surface».
"""
from __future__ import annotations

from widgets import hint_lang as _hl

from . import availability as _av


def _say(key: str, **kw) -> str:
    """The operator-facing line in the agent's language (bundle `widgets.youtube.<key>`)."""
    from i18n import runtime as _rt
    line = _rt.text(f"widgets.youtube.{key}", "", code="en" if _hl.en() else "es")
    for k, v in kw.items():
        line = line.replace("{" + k + "}", str(v))
    return line


def unplayable(db: dict, it: dict) -> bool:
    """Has the embedded player refused this row's video (it is on the blocklist)?"""
    vid = str((it or {}).get("videoId") or "")
    return bool(vid) and vid in _av.blocked_ids(db)


def hint(db: dict, it: dict) -> str:
    """The list row's mark when the player refused it — "" otherwise (`data.ref_index`)."""
    return _say("hint_cannot_play") if unplayable(db, it) else ""


def next_refusal(db: dict) -> "dict | None":
    """`next`'s refusal when what lies ahead cannot play — None to let `next` run as it always did.

    · past the last row while the current one was refused → it is the last one and it cannot play here;
    · the next row refused and no playable row after it → the next one is in the list but cannot play here.
    A playable row further on keeps the old path: it is played, and the player's own swap handles the rest."""
    lst = [it for it in (db.get("list") or []) if isinstance(it, dict)]
    pos = int(db.get("pos", -1))
    nxt = pos + 1
    if not lst:
        return None
    if nxt >= len(lst):
        cur = lst[pos] if 0 <= pos < len(lst) else {}
        if cur and (unplayable(db, cur) or str(db.get("player_error") or "").strip()):
            title = str(cur.get("title") or cur.get("url") or "")[:90]
            return {"ok": False, "error": "end_after_unplayable", "message": _say("end_after_unplayable", title=title)}
        return None
    if unplayable(db, lst[nxt]) and all(unplayable(db, it) for it in lst[nxt:]):
        title = str(lst[nxt].get("title") or lst[nxt].get("url") or "")[:90]
        return {"ok": False, "error": "next_cannot_play", "message": _say("next_cannot_play", title=title)}
    return None
