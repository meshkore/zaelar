"""A viewer, not an editor (V2-457).

The operator asked for "un previsualizador, sin edición, sin funciones extrañas": one picture large, the set as
thumbnails underneath, arrows, a title and its source on top, all of it drivable by voice. Everything here
serves that and stops there — no crop, no filters, no export.

It holds no opinion about where pictures come from. `show` is handed a set that someone else found (the fast
search in `nucleo/flash/image_turn.py`, or a Brain Worker that curated something better) and `local` reads the
files this engine already has on disk. That split is the widget contract: `data.py` is stdlib-only and never
touches the network, so the thing that searches cannot live in here.

The current picture is kept as an INDEX, not as a copy of the item. A viewer whose "current" is a duplicate of
the row goes stale the moment the set is re-sorted or re-fetched, and then the big picture and the highlighted
thumbnail disagree — which is the one bug a picture viewer cannot have.
"""
from __future__ import annotations

import os

from .. import store

WIDGET_ID = "imagenes"
DB_VERSION = 1
# What a browser will actually render. `.svg` is deliberately absent: these come from web search results, and an
# SVG is a document that can carry script, not just a picture.
_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif", ".bmp")
_MAX = 60


def _seed() -> dict:
    return {"title": "", "query": "", "source": "", "items": [], "i": 0}


def _load() -> dict:
    return store.load(WIDGET_ID, _seed(), version=DB_VERSION)


def _clean(it) -> dict:
    """One row, trimmed to what the viewer shows. Anything without a URL is not a picture and is dropped."""
    if not isinstance(it, dict):
        return {}
    url = str(it.get("url") or it.get("image") or "").strip()
    if not url.startswith(("http://", "https://", "/widgets/")):
        return {}
    def _n(v):
        try:
            return int(v)
        except Exception:  # noqa: BLE001
            return 0
    return {
        "url": url,
        "thumb": str(it.get("thumb") or "").strip() or url,
        "title": " ".join(str(it.get("title") or "").split())[:160],
        "site": str(it.get("site") or "").strip()[:80],
        "page": str(it.get("page") or "").strip()[:400],
        "w": _n(it.get("w")), "h": _n(it.get("h")),
        "weight": str(it.get("weight") or "").strip()[:16],
    }


def _rows(raw) -> list:
    out, seen = [], set()
    for it in (raw or []):
        r = _clean(it)
        if not r or r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append(r)
        if len(out) >= _MAX:
            break
    return out


def _clamp(db: dict) -> dict:
    n = len(db.get("items") or [])
    db["i"] = 0 if n == 0 else max(0, min(int(db.get("i") or 0), n - 1))
    return db


def view_data(q: str = "") -> dict:
    db = _clamp(_load())
    items = db.get("items") or []
    i = int(db.get("i") or 0)
    cur = items[i] if items else {}
    return {
        "title": str(db.get("title") or ""),
        "query": str(db.get("query") or ""),
        "source": str(db.get("source") or ""),
        "n": len(items),
        "i": i,
        "current": cur,
        "items": items,
    }


def _resolve(items: list, item) -> "int | None":
    """A spoken reference to one picture → its index. A number is 1-based; text matches the title or the site.

    The operator says "la tercera" or "la de Ferrari", never an array offset — and the model must never guess an
    index either (V2-026), which is why this resolution lives in the widget beside the data it resolves against.
    """
    if item is None:
        return None
    s = str(item).strip()
    if not s:
        return None
    if s.isdigit():
        k = int(s) - 1
        return k if 0 <= k < len(items) else None
    low = s.lower()
    for k, it in enumerate(items):
        if low in str(it.get("title") or "").lower() or low in str(it.get("site") or "").lower():
            return k
    # The model rarely hands over a clean fragment: it says «la que sea claramente del Amalfi» (measured
    # 2026-08-28, three failed selects in one round). A whole-phrase substring cannot match that, but its one
    # meaningful TOKEN can. Longest tokens first so «ferrari amalfi» prefers the more specific word; short
    # tokens (articles, «la», «del») never match anything by construction (>3 chars).
    for tok in sorted((t for t in low.split() if len(t) > 3), key=len, reverse=True):
        for k, it in enumerate(items):
            if tok in str(it.get("title") or "").lower() or tok in str(it.get("site") or "").lower():
                return k
    return None


def ref_index() -> list[dict]:
    """The pictures currently on screen, so voice can name one instead of counting (`widgets/refs.py`)."""
    db = _load()
    out = []
    for k, it in enumerate(db.get("items") or [], 1):
        label = str(it.get("title") or "").strip() or str(it.get("site") or "").strip() or f"foto {k}"
        out.append({"id": str(k), "label": f"{k}. {label}", "field": "item"})
    return out


def _local_files() -> list:
    """Pictures already on this engine's disk, served through the widget's own asset route.

    They live in this widget's data directory because that is the only place a widget is allowed to read and
    write, and `/widgets/<id>/asset/<name>` is the existing route that serves it (path-safe, basename only).
    """
    d = store.data_dir(WIDGET_ID)
    out = []
    try:
        names = sorted(n for n in os.listdir(d) if n.lower().endswith(_EXT))
    except OSError:
        return []
    for n in names:
        out.append({"url": f"/widgets/{WIDGET_ID}/asset/{n}", "title": os.path.splitext(n)[0],
                    "site": "en este equipo", "page": ""})
        if len(out) >= _MAX:
            break
    return out


def apply_action(action: str, payload: dict = None) -> dict:
    p = payload or {}
    a = str(action or "").strip().lower()
    db = _load()
    items = db.get("items") or []

    if a == "show":
        rows = _rows(p.get("items"))
        if not rows:
            # An empty `show` must not blank a set that IS on screen: the operator would be left staring at an
            # empty card with no way back, and the honest report is that nothing was found (V2-377's lesson,
            # applied to pictures).
            return {"ok": False, "error": "no llegó ninguna imagen", "n": len(items)}
        db.update({"items": rows, "i": 0,
                   "title": " ".join(str(p.get("title") or p.get("query") or "").split())[:120],
                   "query": " ".join(str(p.get("query") or "").split())[:120],
                   "source": str(p.get("source") or "")[:40]})
        store.save(WIDGET_ID, _clamp(db))
        return {"ok": True, "n": len(rows), "shown": rows[0].get("title") or rows[0].get("site") or ""}

    if a == "add":
        rows = _rows(list(items) + list(p.get("items") or []))
        added = len(rows) - len(items)
        db["items"] = rows
        store.save(WIDGET_ID, _clamp(db))
        return {"ok": True, "added": added, "n": len(rows)}

    if a == "local":
        rows = _rows(_local_files())
        if not rows:
            return {"ok": False, "error": "no hay imágenes guardadas en este equipo", "n": len(items)}
        db.update({"items": rows, "i": 0, "title": "Imágenes guardadas", "query": "", "source": "local"})
        store.save(WIDGET_ID, _clamp(db))
        return {"ok": True, "n": len(rows), "source": "local"}

    if a in ("select", "next", "previous"):
        if not items:
            return {"ok": False, "error": "no hay ninguna imagen en pantalla", "n": 0}
        if a == "select":
            k = _resolve(items, p.get("item"))
            if k is None:
                # The refusal NAMES what is on screen (V2-463). «no encuentro esa imagen (None)» was measured
                # verbatim in a round: the model had called select with NO item, got told nothing usable, and
                # answered the operator «te la dejo puesta» over a failure — three times. With the choices in
                # the error, the next model turn can actually pick one.
                menu = " · ".join(f"{i}: {str(it.get('title') or it.get('site') or '?')[:40]}"
                                  for i, it in enumerate(items[:6], 1))
                pide = ("dime cuál: un número o parte del título" if not str(p.get("item") or "").strip()
                        else f"no encuentro «{str(p.get('item'))[:60]}»")
                return {"ok": False, "error": f"{pide}. En pantalla: {menu}", "n": len(items)}
        elif a == "next":
            k = (int(db.get("i") or 0) + 1) % len(items)
        else:
            k = (int(db.get("i") or 0) - 1) % len(items)
        db["i"] = k
        store.save(WIDGET_ID, _clamp(db))
        cur = items[k]
        return {"ok": True, "i": k + 1, "n": len(items),
                "shown": cur.get("title") or cur.get("site") or "", "url": cur.get("url") or ""}

    if a == "clear":
        store.save(WIDGET_ID, _seed())
        return {"ok": True, "n": 0}

    return {"ok": False, "error": f"acción desconocida: {action}"}
