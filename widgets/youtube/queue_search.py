"""«Put on a few videos of X, back to back» — search, queue what was found, play the first (V2-781).

Measured in `la-cola-de-video-con-palabras-imprecisas__us` (2026-10-10 20:11): the model answered «I'll line up a
few Maradona videos for you and start the first one» and called `play_video(action=play)` — the only two values the
tool had were ONE video (`load`) or SEVERAL TO CHOOSE FROM (`search`, nothing plays). A queue that starts had no
door, so one video loaded, the queue stayed empty, and «play the second one» failed three turns running («I can't
find that video in the list») until the operator dictated the queue himself on turn 6.

This is that door, built from the two actions that already exist so nothing about them changes: the search paints
the numbered band on Home exactly as `search` does, the first `n` results go to the queue exactly as `add_results`
writes them, and the first of those plays. The queue and the band hold the SAME order, so «the second one» means
the same video whichever of the two the model resolves it against. An existing queue is appended to, never
replaced — his list is his, and a search must not wipe it.
"""
from __future__ import annotations

from . import data as _d

#: How many results «a few videos» queues — the search band's default size, so band and queue coincide.
QUEUE_N = 5


def _count(raw) -> int:
    try:
        n = int(raw or QUEUE_N)
    except Exception:  # noqa: BLE001
        n = QUEUE_N
    return max(2, min(n, 10))


def _a_queue_search(action, p, db) -> dict:
    from . import actions as _a
    n = _count(p.get("n"))
    found = _a._a_search("search", {"query": p.get("query") or p.get("q") or "", "n": n}, db)
    if not found.get("ok"):
        return found
    band = db.get("search_results") or []
    picks = band[:n]
    queued = _a._a_add_results("add_results", {"items": list(range(1, len(picks) + 1))}, db)
    lst = db.get("list") or []
    # The first of the NEW rows plays; when every pick was already queued, the band's first one does (from
    # wherever it sits in his queue), so the order still starts where the search starts.
    first = picks[0].get("videoId") if picks else ""
    idx = (queued.get("positions") or [0])[0] - 1
    if idx < 0:
        idx = next((i for i, it in enumerate(lst) if it.get("videoId") == first), -1)
    if idx < 0:
        return {"ok": False, "error": "no_video", "message": "No encontré vídeos de eso."}
    r = _d._play_pos(db, idx, "play_item")
    r.update({"queued": [str(t.get("title") or "") for t in picks], "count": len(lst),
              "query": found.get("query") or ""})
    return r
