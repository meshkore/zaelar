"""Where a playable item COMES FROM (V2-638) — the player stops being YouTube-only.

`data.py` has said since V2-632 that «`source` travels per row because the widget is provider-agnostic by
design — today every row says "youtube", and a second source is a value, not a schema change». This module is
that second source arriving, and a third: a file in the agent's own library, and a torrent still downloading.

Three sources, one shape. Whatever the row, the player needs exactly two things: what to point at, and how.

    youtube → {"source": "youtube", "videoId": "..."}      the IFrame embed (postMessage control)
    local   → {"source": "local",   "src": "/api/library/stream?path=..."}   a plain <video>
    torrent → {"source": "torrent", "src": "/api/torrent/stream/<id>"}       a plain <video>, still filling

`local` and `torrent` differ only in WHICH route serves the bytes: a finished file goes through the library's
`FileResponse` (Range for free), a live download through the piece-aware route, because the file on disk is
still full of holes until it completes. Everything downstream treats them the same, which is why they share
one `src` field instead of each inventing a way to be played.

Extracted here rather than added to `data.py` because that file sits exactly on the 900-line newborn ceiling
(the `availability.py` / `account.py` precedent): the shelf of video SOURCES was already the most
source-shaped thing in it, so it moves and the per-item source logic joins it.
"""
from __future__ import annotations

YOUTUBE = "youtube"
LOCAL = "local"
TORRENT = "torrent"

# What the player understands. Anything else is treated as YouTube, because every row written before this
# module existed carries no `source` at all and must keep playing exactly as it did.
KNOWN = (YOUTUBE, LOCAL, TORRENT)


def source_of(it) -> str:
    """The source of a row, defaulting to youtube — the value every pre-existing row implies by omission."""
    s = str((it or {}).get("source") or "").strip().lower()
    return s if s in KNOWN else YOUTUBE


def is_stream(it) -> bool:
    """Does this row play through a plain `<video src>` rather than the YouTube embed?"""
    return source_of(it) in (LOCAL, TORRENT)


def connector_shelf(db: dict) -> list:
    """The 🔌 screen: what video sources exist, live or not, with their honest state (V2-632).

    Composed from the V2-526 catalog (data, stdlib json) merged with the live platform rows; fail-soft to []
    — a broken catalog must not blank the player. The shut doors are shown ON PURPOSE (INI-027's wishlist
    rule: what we do NOT have is shown, never narrated)."""
    rows = []
    try:
        from connectors import catalog as _cat
        live = {str(r.get("id") or ""): r for r in (db.get("platforms") or [])}
        for m in _cat.load_manifests():
            if m.get("family") != "video" or m.get("kind") != "connector":
                continue
            pid = str(m.get("id") or "")
            lv = live.get(pid) or {}
            rows.append({"id": pid, "label": str(m.get("label") or pid),
                         "state": str(m.get("state") or "planned"),
                         "connected": bool(lv.get("connected")),
                         "note": str(m.get("why-not") or m.get("notes") or m.get("note") or "")[:220]})
    except Exception:  # noqa: BLE001
        return []
    # YouTube first (the one people ask about), then buildable, then shut doors.
    rank = {"built": 0, "planned": 1, "not-possible": 2}
    rows.sort(key=lambda r: (0 if r["id"] == "youtube" else 1, rank.get(r["state"], 3), r["label"]))
    return rows


def carry(db: dict, it: dict) -> None:
    """Copy a row's SOURCE identity onto the db root, where the player reads it.

    Called from `_play_pos` and the load paths. Always writes both keys, never only the one that applies: a
    stale `src` left behind by the previous item is how a YouTube video ends up playing the last local file's
    bytes, and a stale `source` is how a plain `<video>` gets asked to postMessage."""
    src_kind = source_of(it)
    db["source"] = src_kind
    db["src"] = str(it.get("src") or "") if src_kind in (LOCAL, TORRENT) else ""


def item_from_library(rel: str) -> dict:
    """A player row for a file in the agent's own library, or `{}` if it is not there / not playable."""
    from library import index
    rec = index.entry_for(rel)
    if not rec or rec.get("kind") != "video" or not rec.get("playable"):
        return {}
    return {"source": LOCAL, "videoId": "", "src": rec["url"], "title": rec["name"],
            "channel": "Biblioteca", "published": "", "url": rec["url"], "rel": rec["rel"]}


def item_from_torrent(rid: str, title: str = "") -> dict:
    """A player row for a download in progress — it plays while it fills."""
    from connectors.torrent import service
    return {"source": TORRENT, "videoId": "", "src": service.stream_url(rid),
            "title": title or "Descarga en curso", "channel": "Torrent", "published": "",
            "url": "", "torrent_id": rid}


def play_local(db: dict, path: str) -> dict:
    """Action body: play a file from the library. Returns the row to make current, or an error dict."""
    it = item_from_library(path)
    if not it:
        from library import index
        rec = index.entry_for(path)
        if rec and not rec.get("playable"):
            return {"ok": False, "error": "ese fichero no se puede reproducir en el navegador",
                    "download_url": rec.get("download_url") or ""}
        return {"ok": False, "error": "no encuentro ese vídeo en tu biblioteca"}
    return {"ok": True, "item": it}


def play_torrent(db: dict, query: str = "", magnet: str = "", keep: bool = False) -> dict:
    """Action body: find (or take) a torrent and play its video while it downloads.

    This is the video widget holding the torrent tool directly, which is what the operator asked for — the
    player is where a film is watched, so the download that produces it belongs to the same surface."""
    from connectors.torrent import service
    if not service.available():
        return {"ok": False, "error": service.unavailable_reason()}
    res = (service.add_magnet(magnet, want="video", keep=keep) if magnet
           else service.search_and_play(query, want="video", keep=keep))
    if not res.get("ok"):
        return {"ok": False, "error": res.get("error") or "no pude iniciar la descarga",
                "unplayable": res.get("unplayable") or ""}
    return {"ok": True, "item": item_from_torrent(res["id"], res.get("title") or query)}


def live_status(db: dict) -> dict:
    """Download progress for the row being played, so the card can show it filling. `{}` when not a torrent."""
    if str(db.get("source") or "") != TORRENT:
        return {}
    rid = str(db.get("torrent_id") or "")
    if not rid:
        return {}
    from connectors.torrent import service
    st = service.status(rid)
    return st if isinstance(st, dict) else {}
