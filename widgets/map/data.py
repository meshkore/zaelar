"""Map widget — a handful of places, pinned and numbered, on one map.

Built for the operator's demo script (2026-09-26): «Find me three things I might enjoy doing this weekend» →
«Show them on a map». The agent answered «I don't have a map widget». Places arrive by NAME and/or ADDRESS (what a
search or a results sheet carries); this layer geocodes them — Photon first, Nominatim as the stand-in, both
OpenStreetMap, no key — and stores coordinates. The network lives in `apply_action` only; `view_data` serves the
cache. Stdlib only. The card draws the tiles itself as plain images (widgets/map/widget.js).
"""
from __future__ import annotations

import json
import re
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


def _queries(p: dict, near: str) -> list[str]:
    """The ways to ask for one place, most specific first. A description the caller composed can be what sinks it
    (full27 W1: «Mount Baldy, San Gabriel Mountains, CA» found nothing, «Mount Baldy» alone was found), so the
    place's own name — the first part of what was said — is asked too, with and without the region at the end."""
    full = ", ".join(x for x in (p["name"], p["address"] or near) if x)
    parts = [x.strip() for x in (p["name"] or "").split(",") if x.strip()]
    head = parts[0] if parts else ""
    region = parts[-1] if len(parts) > 1 else (near or "")
    out = [full, p["address"], f"{head}, {region}" if head and region else "", head]
    seen, uniq = set(), []
    for q in out:
        if q and q not in seen:
            seen.add(q)
            uniq.append(q)
    return uniq


def _first_hit(queries: list[str], deadline: float):
    """Ask every way at once, keep the most specific answer that came back — sequentially, three slow tries of ~3 s
    each would not fit the widget pool's deadline."""
    from concurrent.futures import ThreadPoolExecutor
    if not queries:
        return None
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        hits = list(pool.map(lambda q: _geocode(q, deadline), queries))
    return next((h for h in hits if h), None)


def _locate(places: list, near: str, deadline: float) -> tuple[list, list]:
    """Geocode what has no coordinates, within the time left. Returns (placed, missed names), in the order said.

    The places are asked for AT ONCE (demo pass 2026-09-28, W1): one after the other, Photon's ~2 s per place
    spent the whole deadline on the first and «Mount Baldy» and «the Getty» came back missed — the map showed one
    pin and «highlight the second one» had no second one."""
    from concurrent.futures import ThreadPoolExecutor

    def one(p):
        if "lat" in p:
            return p
        if time.time() > deadline:
            return None
        hit = _first_hit(_queries(p, near), deadline)
        if not hit:
            return None
        return {**p, "lat": hit["lat"], "lon": hit["lon"], "address": p["address"] or hit["found"]}
    with ThreadPoolExecutor(max_workers=max(1, min(len(places), 6))) as pool:
        got = list(pool.map(one, places))
    placed = [g for g in got if g]
    missed = [p["name"] for p, g in zip(places, got) if not g]
    return placed, missed


def view_data(q: str = "") -> dict:
    try:
        db = _load()
        return {**{k: db.get(k) for k in _seed()}, "empty": not (db.get("places") or [])}   # V2-776 L2
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


def ref_index() -> list:
    """Voice-referenceable rows — «the second one», «the observatory» — in the shape `widgets/refs` reads
    (V2-773 demo, W2: «Highlight the second one» asked «which one?» because this card published no index)."""
    try:
        return [{"id": str(i + 1), "label": f"{i + 1}. {p.get('name', '')}", "field": "item"}
                for i, p in enumerate(_load().get("places") or [])]
    except Exception:  # noqa: BLE001
        return []


def _numbered(db: dict) -> list:
    return [f"{i + 1}. {p['name']}" for i, p in enumerate(db.get("places") or [])]


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    db = _load()
    deadline = time.time() + 6.5
    if action in ("show", "add"):
        raw = p.get("places") if p.get("places") is not None else (p.get("items") or p.get("points"))
        if isinstance(raw, str) and ("," in raw or re.search(r"\s(and|y|&)\s", raw, re.I)):
            # ONE text that may be SEVERAL places (demo pass 79, 2026-10-03, W1): «Griffith Observatory, Mount
            # Baldy, The Getty» was pinned as one place, and «highlight the second one» failed with «(1-1)» while
            # the model said it highlighted Mount Baldy. Splitting on commas is no answer — «Griffith Observatory,
            # Los Angeles» is ONE place with its city — so the call is sent back for a list, and the data-op loop
            # corrects it in the same turn. A JSON list sent as text is decoded at the payload door (contract).
            return {"ok": False, "error": "'places' must be a LIST with one entry per place — e.g. "
                                          "[{\"name\": \"Griffith Observatory\"}, {\"name\": \"Mount Baldy\"}] — "
                                          "a single text could be one place or several"}
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
