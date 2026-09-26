"""Map widget — a handful of places, pinned and numbered, on one map.

Built for the operator's demo script (2026-09-26): «Find me three things I might enjoy doing this weekend» →
«Show them on a map». The agent answered «I don't have a map widget». Places arrive by NAME and/or ADDRESS (what a
search or a results sheet carries); this layer geocodes them — Photon first, Nominatim as the stand-in, both
OpenStreetMap, no key — and stores coordinates. The network lives in `apply_action` only; `view_data` serves the
cache. Stdlib only. The card draws the tiles itself as plain images (widgets/map/widget.js).
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

from .. import store

WID = "map"
_UA = "zaelar-personal-agent/1.0 (+https://zaelar.com)"
_TIMEOUT_S = 2.5           # a whole action must fit the widget pool's 8 s
_MAX_PLACES = 12


def _seed() -> dict:
    return {"title": "", "places": [], "selected": 0, "updated": 0, "misses": []}


def _load() -> dict:
    return store.load(WID, _seed())


_MIN_CALL_S = 0.4          # below this there is no point asking: the answer cannot arrive in time


def _get(url: str, timeout: float = _TIMEOUT_S):
    req = urllib.request.Request(url, headers={"User-Agent": _UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _geocode(query: str, deadline: float | None = None) -> dict | None:
    """(lat, lon, label) for a place said by name/address. None when neither service knows it — or when the
    `deadline` leaves no time to ask: each call is capped at what is LEFT, so three slow places cannot add up
    to four services × 2.5 s past the widget pool's 8 s (V2-773 audit; the deadline used to be read only
    between places, and one place started with a second to spare could run ten)."""
    q = " ".join(str(query or "").split())[:200]
    if not q:
        return None

    def _left() -> float:
        return _TIMEOUT_S if deadline is None else min(_TIMEOUT_S, deadline - time.time())
    try:
        if _left() < _MIN_CALL_S:
            return None
        got = _get("https://photon.komoot.io/api/?" + urllib.parse.urlencode({"q": q, "limit": 1}), _left())
        f = (got.get("features") or [None])[0]
        if f:
            lon, lat = f["geometry"]["coordinates"][:2]
            p = f.get("properties") or {}
            parts = [p.get("street"), p.get("city") or p.get("locality"), p.get("state")]
            return {"lat": float(lat), "lon": float(lon), "found": ", ".join(x for x in parts if x)}
    except Exception:  # noqa: BLE001 — fall through to the stand-in
        pass
    try:
        if _left() < _MIN_CALL_S:
            return None
        got = _get("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
            {"q": q, "format": "json", "limit": 1}), _left())
        if got:
            return {"lat": float(got[0]["lat"]), "lon": float(got[0]["lon"]),
                    "found": str(got[0].get("display_name") or "")[:120]}
    except Exception:  # noqa: BLE001
        pass
    return None


def _clean(raw) -> dict | None:
    if isinstance(raw, str):
        raw = {"name": raw}
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("title") or raw.get("label") or "").strip()[:120]
    addr = str(raw.get("address") or raw.get("location") or raw.get("where") or "").strip()[:200]
    if not name and not addr:
        return None
    out = {"name": name or addr, "address": addr, "note": str(raw.get("note") or raw.get("why") or "").strip()[:160],
           "url": str(raw.get("url") or raw.get("link") or "").strip()[:500]}
    try:
        if raw.get("lat") is not None and raw.get("lon", raw.get("lng")) is not None:
            out["lat"], out["lon"] = float(raw["lat"]), float(raw.get("lon", raw.get("lng")))
    except (TypeError, ValueError):
        pass
    return out


def _places_in(payload: dict) -> list:
    raw = payload.get("places") or payload.get("items") or payload.get("points") or []
    if isinstance(raw, (str, dict)):
        raw = [raw]
    return [p for p in (_clean(r) for r in raw) if p][:_MAX_PLACES]


def _locate(places: list, near: str, deadline: float) -> tuple[list, list]:
    """Geocode what has no coordinates, within the time left. Returns (placed, missed names)."""
    placed, missed = [], []
    for p in places:
        if "lat" not in p:
            if time.time() > deadline:
                missed.append(p["name"])
                continue
            q = ", ".join(x for x in (p["name"], p["address"] or near) if x)
            hit = _geocode(q, deadline) or (_geocode(p["address"], deadline) if p["address"] else None)
            if not hit:
                missed.append(p["name"])
                continue
            p = {**p, "lat": hit["lat"], "lon": hit["lon"], "address": p["address"] or hit["found"]}
        placed.append(p)
    return placed, missed


def view_data(q: str = "") -> dict:
    try:
        db = _load()
        return {k: db.get(k) for k in _seed()}
    except Exception as e:  # noqa: BLE001 — never raise from the hot path
        return {**_seed(), "error": str(e)[:160]}


def prompt_digest() -> str:
    try:
        db = _load()
        ps = db.get("places") or []
        if not ps:
            return ""
        rows = "; ".join(f"{i + 1}. {p['name']}" + (f" ({p['address']})" if p.get("address") else "")
                         for i, p in enumerate(ps))
        return f"Map on screen{(' — ' + db['title']) if db.get('title') else ''}: {rows}."
    except Exception:  # noqa: BLE001
        return ""


def _numbered(db: dict) -> list:
    return [f"{i + 1}. {p['name']}" for i, p in enumerate(db.get("places") or [])]


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()
    deadline = time.time() + 6.5
    if action in ("show", "add"):
        incoming = _places_in(p)
        if not incoming:
            return {"ok": False, "error": "no places arrived — send 'places' as a list of {name, address} "
                                          "(the address can be just the city: «Griffith Observatory, Los Angeles»)"}
        near = str(p.get("near") or p.get("city") or "").strip()
        placed, missed = _locate(incoming, near, deadline)
        if not placed:
            return {"ok": False, "error": f"I could not find any of those on the map ({', '.join(missed)}) — "
                                          "send an address or the city with each name"}
        base = [] if action == "show" else list(db.get("places") or [])
        db["places"] = (base + placed)[:_MAX_PLACES]
        if action == "show":
            db["title"] = str(p.get("title") or p.get("query") or "").strip()[:80]
            db["selected"] = 0
        db["misses"], db["updated"] = missed, int(time.time())
        store.save(WID, db)
        return {"ok": True, "places": _numbered(db), "not_found": missed}
    if action == "select":
        ps = db.get("places") or []
        item = str(p.get("item") or p.get("n") or p.get("name") or "").strip()
        idx = None
        if item.isdigit() and 1 <= int(item) <= len(ps):
            idx = int(item)
        else:
            low = item.lower()
            hits = [i + 1 for i, x in enumerate(ps) if low and low in x["name"].lower()]
            idx = hits[0] if len(hits) == 1 else None
        if idx is None:
            return {"ok": False, "error": "which one? say its number on the map (1-%d) or its name" % len(ps),
                    "places": _numbered(db)}
        db["selected"] = idx
        store.save(WID, db)
        sel = ps[idx - 1]
        return {"ok": True, "selected": idx, "name": sel["name"], "address": sel.get("address", ""),
                "url": sel.get("url", "")}
    if action == "clear":
        store.save(WID, _seed())
        return {"ok": True}
    return {"ok": False, "error": f"unknown action '{action}' — map has show, add, select, clear"}
