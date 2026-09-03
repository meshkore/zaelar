#
# store.py — the durable local index of imported photos (V2-564). This is what makes the Fotos widget
# possible at all: Google's Picker never gives a standing feed of "the whole library" (see `providers.py`),
# so whatever gets picked has to be remembered locally, forever, or it is gone the moment the picker session
# expires. This module is the one place that fact lives.
#
# Lives under the FOTOS WIDGET's own data directory (`widgets/store.data_dir("fotos")`) — the same pattern
# `connectors/telegram/service.py`, `connectors/email/service.py` and `connectors/whatsapp/bridge_proc.py`
# already use to reach a widget's storage from inside a connector, for the same reason: this connector exists
# to feed exactly one widget, not a shared resource other widgets could read.
#
# Photo BYTES are never kept in the JSON index — only a path to a small cached thumbnail under `thumbs/`. A
# `baseUrl` from Google is a signed, ~hour-lived link (see `google_photos.py`); the thumbnail file is what
# survives past that.
#
from __future__ import annotations

import os
import time
from pathlib import Path

from connectors.secure_json_store import SecureJsonStore


def _data_dir() -> Path:
    from widgets import store as _wstore
    return Path(_wstore.data_dir("fotos"))


def _index_path() -> Path:
    return _data_dir() / "index.json"


def thumbs_dir() -> Path:
    d = _data_dir() / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def thumb_path(item_id: str) -> Path:
    safe = "".join(c for c in str(item_id) if c.isalnum() or c in "-_")
    return thumbs_dir() / f"{safe}.jpg"


def _seed() -> dict:
    return {"items": {}, "order": [], "batches": {}, "pending_session": {}}


def load() -> dict:
    d = SecureJsonStore(_index_path()).load()
    seed = _seed()
    for k, v in seed.items():
        d.setdefault(k, v)
    return d


def save(data: dict) -> None:
    SecureJsonStore(_index_path()).save(data)


# ── picker session (one at a time — a second "connect" replaces the pending one) ─────────────────────────────
def pending_session() -> dict:
    return load().get("pending_session") or {}


def set_pending_session(session: dict | None) -> None:
    d = load()
    d["pending_session"] = dict(session or {})
    save(d)


# ── batches (one per import — what a voice-given trip label attaches to) ─────────────────────────────────────
def new_batch_id() -> str:
    return f"b{int(time.time() * 1000)}"


def add_batch(item_ids: list[str], provider: str, label: str = "") -> str:
    d = load()
    bid = new_batch_id()
    d["batches"][bid] = {
        "id": bid, "created_at": int(time.time()), "provider": provider,
        "label": str(label or "").strip(), "item_ids": list(item_ids or []),
    }
    save(d)
    return bid


def label_batch(batch_id: str, label: str) -> bool:
    d = load()
    b = d.get("batches", {}).get(batch_id)
    if not b:
        return False
    b["label"] = str(label or "").strip()
    save(d)
    return True


def last_batch_id() -> str:
    d = load()
    batches = d.get("batches") or {}
    if not batches:
        return ""
    return max(batches.values(), key=lambda b: b.get("created_at") or 0).get("id") or ""


def batch_label_for_item(item_id: str, d: dict | None = None) -> str:
    d = d if d is not None else load()
    for b in (d.get("batches") or {}).values():
        if item_id in (b.get("item_ids") or []):
            return str(b.get("label") or "")
    return ""


# ── items ──────────────────────────────────────────────────────────────────────────────────────────────────
def upsert_items(items: list[dict], batch_id: str) -> int:
    """Merge normalized entries into the index (re-importing the same item overwrites its metadata, never
    duplicates it — the item `id` from the provider is the key). Returns how many were new."""
    d = load()
    new = 0
    for it in items or []:
        iid = str(it.get("id") or "")
        if not iid:
            continue
        if iid not in d["items"]:
            d["order"].append(iid)
            new += 1
        d["items"][iid] = it
    save(d)
    return new


def all_items(d: dict | None = None) -> list[dict]:
    """Every imported item, newest `taken_at` first. Items with no date sort AFTER every dated one, at their
    original import order — not `sort(reverse=True)` on a `(has_date, date)` tuple, which reverses BOTH
    fields at once and puts the undated group first instead of last."""
    d = d if d is not None else load()
    items = list((d.get("items") or {}).values())
    dated = [it for it in items if it.get("taken_at")]
    undated = [it for it in items if not it.get("taken_at")]
    dated.sort(key=lambda it: it["taken_at"], reverse=True)
    return dated + undated


def years_summary(d: dict | None = None) -> list[dict]:
    """[{year, count}] descending — what the gallery's sticky section headers are built from. Computed HERE,
    server-side, so `widget.js` never has to bucket a thousand dates itself."""
    d = d if d is not None else load()
    counts: dict[str, int] = {}
    for it in (d.get("items") or {}).values():
        ta = str(it.get("taken_at") or "")
        year = ta[:4] if len(ta) >= 4 and ta[:4].isdigit() else "?"
        counts[year] = counts.get(year, 0) + 1
    return [{"year": y, "count": c} for y, c in sorted(counts.items(), key=lambda kv: kv[0], reverse=True)]


def page(offset: int, size: int, d: dict | None = None) -> dict:
    d = d if d is not None else load()
    items = all_items(d)
    total = len(items)
    offset = max(0, int(offset or 0))
    size = max(1, min(int(size or 120), 500))
    sl = items[offset:offset + size]
    return {"items": sl, "next_offset": offset + len(sl), "has_more": offset + len(sl) < total, "total": total}


def filter_items(date_from: str = "", date_to: str = "", label_substr: str = "",
                  d: dict | None = None) -> list[dict]:
    """Items whose `taken_at` falls in [date_from, date_to] (either bound optional, ISO `YYYY-MM-DD` strings,
    compared as plain strings which sort correctly for that format) AND whose batch label or filename contains
    `label_substr` (case-insensitive substring, empty = no label filter)."""
    d = d if d is not None else load()
    needle = str(label_substr or "").strip().lower()
    out = []
    for it in all_items(d):
        ta = str(it.get("taken_at") or "")
        if date_from and ta and ta < date_from:
            continue
        if date_to and ta and ta > date_to:
            continue
        if date_from and not ta:      # a date-bounded search skips undated items rather than guessing
            continue
        if needle:
            label = batch_label_for_item(str(it.get("id") or ""), d).lower()
            name = str(it.get("filename") or "").lower()
            if needle not in label and needle not in name:
                continue
        out.append(it)
    return out


def item_count(d: dict | None = None) -> int:
    d = d if d is not None else load()
    return len(d.get("items") or {})
