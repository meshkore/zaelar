#
# server/memory_viewer_api.py — the HTTP face of the memory viewer (V2-808, V2-814): a MONITOR of everything the
# agent keeps — counted, sized and charted over time — never a browser of the stored rows.
#
#   * `GET /api/memory/viewer/stats` — one card per store: its total, a breakdown (sources, types, sizes) and its
#     last 30 days. COUNTs and a directory walk (cached), never a row;
#   * `GET /api/memory/viewer/graph|concept|timeline` — the concept graph, aggregated by `memory.viewer` and
#     bounded by the node budget the client sends; a concept is numbers and related concepts, never text;
#   * `GET /api/memory/viewer/cards` — the «Cards» tab (V2-815): the newest cards of each layer, capped per layer
#     and cut on the server, so a growing store never grows what the browser paints.
#
# Nothing here says anything about the machine it runs on: the viewer talks about what is stored, not where.
# Each store is read through its owner where the owner has a read (memory, the message archive, the widget
# store); the tables with no read of their own (rules, learnt phrases, the event log, the vault) are COUNTED
# through a read-only connection — a number, never a row, and for the vault never anything but the number.
#
import asyncio
import mimetypes
import os
import sqlite3
import time
from datetime import date, timedelta

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from memory import api as memapi
from widgets.mensajeria import media as _media

from .memory_viewer_apps import (  # noqa: F401 — moved, imported back under their names
    _dir_rows, _dirs, _lock, _measure_dirs, _widgets_root)

router = APIRouter()

#: What a connector writes into the messaging data dir — the same prefixes its media sweep owns.
# The stored-file prefixes are declared once, where the files are written (`widgets/mensajeria/media.py`).
_MEDIA_PREFIXES = _media.PREFIXES
#: Days of the per-store series.
SERIES_DAYS = 30


def _file_type(name: str) -> str:
    """The overview's type for a stored file, read from its declared media type (the file name's extension)."""
    kind = (mimetypes.guess_type(name)[0] or "").split("/")[0]
    return {"image": "images", "video": "videos", "audio": "audio"}.get(kind, "documents")


def _is_image(name: str) -> bool:
    """A raster image by its declared type."""
    kind = mimetypes.guess_type(name)[0] or ""
    return kind.startswith("image/") and "svg" not in kind
_STATS_TTL_S = 8.0

_stats_cache: dict = {"at": 0.0, "body": None}
_media_cache: dict = {"at": 0.0, "rows": None}


# ── counts of the tables that have no read of their own ─────────────────────────────────────────────────────
def _table_counts() -> dict:
    from bus import log as buslog
    out = {"rules": 0, "phrases": 0, "paraphrases": 0, "events": 0, "events_week": 0, "vault": 0, "tasks": 0,
           "events_daily": {}, "sessions": 0, "session_days": 0, "sessions_since": 0, "sessions_daily": {}}
    path = str(buslog.db_path())
    if not os.path.exists(path):
        return out
    week_ms = (time.time() - 7 * 86400) * 1000
    queries = {"rules": ("SELECT COUNT(*) FROM rules", ()), "phrases": ("SELECT COUNT(*) FROM action_map", ()),
               "paraphrases": ("SELECT COUNT(*) FROM paraphrase_index", ()),
               "events": ("SELECT COUNT(*) FROM events", ()),
               "events_week": ("SELECT COUNT(*) FROM events WHERE ts_ms >= ?", (week_ms,)),
               "vault": ("SELECT COUNT(*) FROM vault_secrets", ()), "tasks": ("SELECT COUNT(*) FROM tasks", ())}
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    try:
        have = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for key, (sql, args) in queries.items():
            table = sql.split(" FROM ")[1].split()[0]
            if table in have:
                out[key] = int(conn.execute(sql, args).fetchone()[0] or 0)
        if "events" in have:
            since_ms = (time.time() - SERIES_DAYS * 86400) * 1000
            day = "date(ts_ms/1000,'unixepoch','localtime')"
            out["events_daily"] = {r[0]: int(r[1]) for r in conn.execute(
                f"SELECT {day} d, COUNT(*) FROM events WHERE ts_ms >= ? GROUP BY d", (since_ms,))}
            # His sessions with the agent: the event log is the only store that knows a session; it keeps them
            # for its retention window, so these are the sessions on record, not every one there ever was.
            r = conn.execute(f"SELECT COUNT(DISTINCT session_id), COUNT(DISTINCT {day}), MIN(ts_ms) FROM events "
                             "WHERE session_id IS NOT NULL AND session_id != ''").fetchone()
            out["sessions"], out["session_days"], out["sessions_since"] = \
                int(r[0] or 0), int(r[1] or 0), int((r[2] or 0) / 1000)
            out["sessions_daily"] = {d: int(n) for d, n in conn.execute(
                f"SELECT {day} d, COUNT(DISTINCT session_id) FROM events WHERE ts_ms >= ? AND session_id IS NOT NULL "
                "AND session_id != '' GROUP BY d", (since_ms,))}
    finally:
        conn.close()
    return out


# ── files: the media the connectors downloaded + what he dropped on the agent ──────────────────────────────
def _media_rows() -> list[dict]:
    """The media files, newest first. A directory listing (no content read), cached 30 s."""
    now = time.monotonic()
    with _lock:
        if _media_cache["rows"] is not None and now - _media_cache["at"] < 30:
            return _media_cache["rows"]
    folder = os.path.join(_widgets_root(), "mensajeria")
    rows = []
    if os.path.isdir(folder):
        for e in os.scandir(folder):
            if e.is_file(follow_symlinks=False) and e.name.startswith(_MEDIA_PREFIXES):
                st = e.stat(follow_symlinks=False)
                kind = e.name.split("_", 1)[0]
                if _is_image(e.name):
                    kind = "img"
                rows.append({"name": e.name, "kind": kind, "bytes": st.st_size, "mtime": int(st.st_mtime)})
    rows.sort(key=lambda r: (-r["mtime"], r["name"]))
    with _lock:
        _media_cache.update(at=now, rows=rows)
    return rows


# ── stats ───────────────────────────────────────────────────────────────────────────────────────────────────
def _contacts_and_agenda() -> dict:
    from widgets import store
    c = store.load("contactos", {}) if store.exists("contactos") else {}
    a = store.load("agenda", {}) if store.exists("agenda") else {}
    return {"contacts": len(c.get("contacts") or []), "meetings": len(a.get("meetings") or []),
            "todo": len(a.get("tasks") or []) + len(a.get("recurring") or [])}


def _series(by_day: dict, days: int = SERIES_DAYS) -> list[int]:
    """A {local-date: n} map → the last `days` values, oldest first, zeros where nothing happened."""
    today = date.today()
    return [int(by_day.get((today - timedelta(days=i)).isoformat(), 0)) for i in range(days - 1, -1, -1)]


def _files(media: list[dict], eps: list[dict]) -> dict:
    """The files he has, by TYPE: how many and how much each type takes, and how many arrived each day."""
    types: dict[str, dict] = {}
    daily: dict[str, int] = {}
    for r in media:
        t = _file_type(r["name"])
        g = types.setdefault(t, {"n": 0, "bytes": 0})
        g["n"] += 1; g["bytes"] += r["bytes"]
        d = date.fromtimestamp(r["mtime"]).isoformat()
        daily[d] = daily.get(d, 0) + 1
    if eps:
        g = types.setdefault("documents", {"n": 0, "bytes": 0})
        g["n"] += len(eps); g["bytes"] += sum(int(e.get("bytes") or 0) for e in eps)
    return {"types": types, "daily": daily}


def _stats() -> dict:
    from connectors.messaging import archive
    mem = memapi.viewer.counts()
    msgs = archive.totals()
    tables = _table_counts()
    files = _files(_media_rows(), memapi.list_episodes())
    ca = _contacts_and_agenda()
    dirs = _dir_rows()
    rules = tables["rules"] or len((memapi.state() or {}).get("rules") or [])
    mem_daily = {r["day"]: r["own"] for r in memapi.viewer.per_day(SERIES_DAYS)}
    msg_daily = {r["day"]: r["messages"] for r in archive.per_day(SERIES_DAYS)}
    ftypes = files["types"]
    stores = [
        {"key": "memories", "total": mem["facts"], "week": mem["facts_week"], "daily": _series(mem_daily),
         "parts": {"concepts": mem["concepts"], "relations": mem["relations"], "short": mem["facts_short"],
                   "long": mem["facts"] - mem["facts_short"]}},
        {"key": "conversation", "total": tables["sessions"], "since": tables["sessions_since"],
         "daily": _series(tables["sessions_daily"]),
         "parts": {"days": tables["session_days"], "turns": mem["conversation"]}},
        {"key": "messages", "total": msgs["total"], "bytes": msgs["bytes"], "week": msgs["week"],
         "daily": _series(msg_daily), "parts": msgs["by_platform"]},
        {"key": "files", "total": sum(g["n"] for g in ftypes.values()),
         "bytes": sum(g["bytes"] for g in ftypes.values()), "daily": _series(files["daily"]),
         "types": ftypes},
        {"key": "contacts", "total": ca["contacts"]},
        {"key": "agenda", "total": ca["meetings"] + ca["todo"] + tables["tasks"],
         "parts": {"meetings": ca["meetings"], "todo": ca["todo"], "errands": tables["tasks"]}},
        {"key": "apps", "total": None if dirs is None else sum(g["bytes"] for g in dirs), "unit": "bytes",
         "pending": dirs is None,
         "apps": [] if dirs is None else [{"key": g["key"], "title": g.get("title", ""), "bytes": g["bytes"],
                                           "sheets": g.get("sheets", 0)} for g in dirs if g["bytes"]]},
        {"key": "rules", "total": rules},
        {"key": "phrases", "total": tables["phrases"], "parts": {"paraphrases": tables["paraphrases"]}},
        {"key": "events", "total": tables["events"], "week": tables["events_week"],
         "daily": _series(tables["events_daily"])},
        {"key": "vault", "total": tables["vault"]},
    ]
    return {"stores": stores, "counted_at": int(time.time())}


@router.get("/api/memory/viewer/stats")
async def viewer_stats():
    """Every store, totalled. Cached a few seconds: the overview and a live refresh share one count."""
    now = time.monotonic()
    body = _stats_cache["body"]
    stale = body is None or now - _stats_cache["at"] >= _STATS_TTL_S
    if stale or (_apps_pending(body) and _dirs["rows"] is not None):
        body = await asyncio.to_thread(_stats)
        _stats_cache.update(at=now, body=body)
    return JSONResponse(body, headers={"Cache-Control": "no-cache"})


def _apps_pending(body: dict | None) -> bool:
    return bool(body) and any(s.get("pending") for s in body.get("stores") or [])


# ── memory: graph, concept, timeline ───────────────────────────────────────────────────────────────────────
@router.get("/api/memory/viewer/graph")
async def viewer_graph(days: int = 30, layers: str = "short,long", lanes: str = "own", budget: int = 300):
    body = await asyncio.to_thread(memapi.viewer.graph, days=days, layers=layers, lanes=lanes, budget=budget)
    body["layer_counts"] = await asyncio.to_thread(memapi.viewer.layer_counts, days=days)
    return JSONResponse(body, headers={"Cache-Control": "no-cache"})


@router.get("/api/memory/viewer/concept")
async def viewer_concept(key: str, days: int = 30, layers: str = "short,long", lanes: str = "own"):
    return await asyncio.to_thread(memapi.viewer.concept, key, days=days, layers=layers, lanes=lanes)


@router.get("/api/memory/viewer/cards")
async def viewer_cards(limit: int = 100):
    """The «Cards» tab: the newest cards per layer, bounded and cut on the server (`memory.viewer.cards`)."""
    return JSONResponse(await asyncio.to_thread(memapi.viewer.cards, limit), headers={"Cache-Control": "no-cache"})


@router.get("/api/memory/viewer/timeline")
async def viewer_timeline(days: int = 30):
    return {"days": await asyncio.to_thread(memapi.viewer.per_day, days)}
