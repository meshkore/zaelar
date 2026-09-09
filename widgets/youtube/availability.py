"""widgets/youtube/availability.py — what happens when the embedded player REFUSES a video (V2-634).

Extracted from data.py paying the newborn-file ceiling; one cohesive concern: the blocklist of videos the
player reported unplayable (101/150 = the owner disables embedding — the copyright case; 100 removed; 2/5
broken), the swap that replaces OUR OWN pick with the next playable candidate, and the notice that carries
the fact to the card's banner and the brain. The operator's rule, verbatim in spirit: «si es un vídeo que
buscamos nosotros mismos y no se puede reproducir, no lo pongas: pon el siguiente. Si el usuario te pegara
un enlace, muéstrale el mensaje del copyright y díselo».

`_search_id` is injected by data.py at import (the account.py seam pattern, V2-632): the re-resolve of a
dead pick's query must go through the SAME search door every other resolution uses, blocklists included.
"""
from __future__ import annotations

import time

from widgets.youtube import library

_search_id = None                 # injected by data.py (V2-632 seam pattern)

# V2-634 — the embedded player's fatal codes (IFrame API onError): 101/150 = the owner disables embedding
# (the copyright case), 100 = removed/private, 2/5 = broken. Any of them means THIS surface cannot play it.
FATAL_CODES = {"2", "5", "100", "101", "150"}


def blocked_ids(db: dict) -> set:
    return {str(b.get("videoId") or "") for b in (db.get("blocked_videos") or [])}


def remember_blocked(db: dict, vid: str, title: str, code: str) -> None:
    """Record an unplayable video so no search or swap ever offers it again (cap 30, oldest out)."""
    if not vid or vid in blocked_ids(db):
        return
    lst = list(db.get("blocked_videos") or [])
    lst.append({"videoId": vid, "title": (title or "")[:120], "code": code, "at": int(time.time())})
    db["blocked_videos"] = lst[-30:]


def swap_to(db: dict, it: dict) -> None:
    """Make `it` the current video (the play_result field set, shared shape). Caller saves."""
    db["player_error"] = ""
    db["blocked_notice"] = {}
    db["videoId"] = str(it.get("videoId") or "")
    db["url"] = it.get("url") or ("https://www.youtube.com/watch?v=" + db["videoId"])
    db["title"] = it.get("title") or db["url"]
    db["channel"] = it.get("channel") or ""
    db["published"] = it.get("published") or ""
    db["latest"] = False
    db["pos"] = next((j for j, x in enumerate(db.get("list") or [])
                      if x.get("videoId") == db["videoId"]), -1)
    db["paused"] = False
    db["pick_explicit"] = False
    library.record_play(db, it)
    library.apply_prefs(db, fresh=False)


def next_unblocked(db: dict, dead: str) -> "dict | None":
    """The replacement for a video OUR side picked and the player refused: the queue's next playable item
    when the dead one was playing FROM the queue, else the search band's next playable result, else the
    same search re-resolved with the blocklist applied. None = nothing honest to offer."""
    bids = blocked_ids(db)
    pos = int(db.get("pos", -1))
    if pos >= 0:
        for it in (db.get("list") or [])[pos + 1:]:
            if str(it.get("videoId") or "") not in bids:
                return it
    for it in (db.get("search_results") or []):
        v = str(it.get("videoId") or "")
        if v and v != dead and v not in bids:
            return it
    q = str(db.get("last_query") or "").strip()
    if q:
        r = _search_id(q, db.get("blocked_channels"), bids)
        if r.get("videoId"):
            return {"videoId": r["videoId"], "title": r["title"], "channel": r["channel"],
                    "published": r["published"]}
    return None




def notice_lines(db: dict) -> list:
    """The blocked-playback fact, phrased for the model (prompt_digest): say it, never re-narrate it."""
    bn = db.get("blocked_notice") or {}
    k = bn.get("kind")
    if k == "swapped":
        return [f"AVISO DEL REPRODUCTOR: «{bn.get('from','')}» no se pudo reproducir aquí (su propietario "
                f"bloquea la inserción) y YA se puso «{bn.get('to','')}» en su lugar — si el operador "
                "pregunta, dilo tal cual; no lo recargues ni lo vuelvas a buscar."]
    if k == "explicit":
        return [f"AVISO DEL REPRODUCTOR: el vídeo que el operador pidió («{bn.get('from','')}») solo puede "
                "verse en YouTube — su propietario bloquea la reproducción embebida. Díselo claro; NO lo "
                "recargues ni finjas que se reproduce."]
    if k == "exhausted":
        return [f"AVISO DEL REPRODUCTOR: «{bn.get('from','')}» está bloqueado para inserción y no encontré "
                "sustituto reproducible — pídele otra búsqueda o el enlace."]
    return []


def on_player_error(db: dict, code: str, dead: str) -> "str | None":
    """Handle one onError report. Returns "stale" (late report for an already-replaced video — blocklisted,
    nothing else), "handled" (fatal, acted on), or None (non-fatal: caller just records the code)."""
    cur = str(db.get("videoId") or "")
    if code not in FATAL_CODES or not dead:
        return None
    remember_blocked(db, dead, str(db.get("title") or "")[:100] if dead == cur else "", code)
    if dead != cur:
        # A LATE report: the failing video was already replaced by the time this arrived — it is blocklisted
        # above and its successor must not inherit the blame (the report names its video precisely so this
        # attribution race cannot happen).
        return "stale"
    db["player_error"] = code
    dead_title = str(db.get("title") or "")[:100]
    if db.get("pick_explicit"):
        # He handed this exact video over — the honest message, EVERY time it is tried, never a swap.
        db["blocked_notice"] = {"kind": "explicit", "from": dead_title, "code": code}
        return "handled"
    nxt = next_unblocked(db, dead)
    if nxt is None:
        db["blocked_notice"] = {"kind": "exhausted", "from": dead_title, "code": code}
        return "handled"
    swap_to(db, nxt)
    db["blocked_notice"] = {"kind": "swapped", "from": dead_title,
                            "to": str(db.get("title") or "")[:100], "code": code}
    return "handled"
