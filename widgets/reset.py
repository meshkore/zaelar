"""widgets/reset.py — LEAVE SURFACES BLANK when the operator presses Reset.

Until now, reset closed cards but did NOT touch their data, so content remained waiting there: the operator reset "to
start from scratch", requested a new search, and when the results sheet opened it showed the ENTIRE previous search
(Ibiza ferries from August 10) while the worker for the new one was still running. A widget showing previous work as
if it were current work is the same kind of failure as a down agent painted blue: it is not ugly, it is MISLEADING.

**What is emptied and what is not.** Reset preserves credentials and authentication (that is its contract, and the
dialog says so), so here only each widget's `state.json` is touched — never its `data_dir`, where captures and,
especially, **the browser's Chromium profile with sessions manually opened by the operator** live. Deleting the whole
folder (what `store.delete` does, intended for when the widget DIES) would cost them all their logins.

And there is a boundary the operator must be able to move without touching code: **DERIVED data vs the operator's
RECORD**. A results sheet, report, or chart is the output of work — reproducible, and emptying it loses nothing. The
agenda, however, is their REAL projects, tasks, and appointments: that is not the output of anything, and deleting it
would be loss. A widget declares this in its manifest:

    "data": { "durable": true }     → reset does NOT touch it (it is the operator's record)

Without declaring it, it is emptied. That is the default the operator requested ("all result/visualization/etc.
widgets must initialize blank"), and it leaves the exception explicit, reviewable, and in the widget itself instead
of a hidden list here.

**How it is emptied** (from most specific to most generic, first winner):
  1. `data.py::blank()` — the widget decides what "blank" means for it. Messaging needs this: its messages go away,
     but each platform's CONNECTION state remains (otherwise reset would look like disconnecting you from WhatsApp).
  2. `data.py::_empty()` — the convention that already existed in several widgets for their seed state.
  3. delete `state.json` — generic and safe: `store.load` falls back to the default passed by the widget itself, i.e.
     its empty sheet. Never touches the rest of `data_dir`.
"""
from __future__ import annotations

import inspect
import json
import os

from loguru import logger

from . import store
from .server_api import _data_module


def _manifest(widget_id: str) -> dict:
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), widget_id, "manifest.json")
        with open(p, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def is_durable(widget_id: str) -> bool:
    """Is its content the operator's RECORD (agenda, contacts...) instead of the output of work?
    Only True if the widget DECLARES it. When in doubt, empty it: that is what the operator requested."""
    return bool((_manifest(widget_id).get("data") or {}).get("durable"))


def _has_state(widget_id: str) -> bool:
    return os.path.exists(os.path.join(store.data_dir(widget_id), "state.json"))


def _blank_one(widget_id: str) -> str:
    """Empty ONE widget. Returns how it was done ('blank' | 'empty' | 'wiped' | 'error'). Never raises."""
    mod = _data_module(widget_id)          # None if the widget has no data.py (or its code no longer exists)
    # (1) the widget knows what "blank" means for it (preserves non-content: connections, settings...)
    for name in ("blank", "_empty"):
        fn = getattr(mod, name, None) if mod else None
        if not callable(fn):
            continue
        try:
            if inspect.signature(fn).parameters:      # `_empty(reason)` and friends: not an empty seed state
                continue
            data = fn()
            if isinstance(data, dict):
                store.save(widget_id, data)                # already announces the change to the canvas (`widget/data`)
                # ...but plain `data` does not say this was a RESET: `_announce` writes the audit row.
                _announce(widget_id, "blank" if name == "blank" else "empty", refresh=False)
                return "blank" if name == "blank" else "empty"
        except Exception as e:  # noqa: BLE001
            logger.warning(f"widgets.reset: {widget_id}.{name}() falló: {e}")
    # (2) generic: remove state and let the widget rebuild it blank. ONLY state.json.
    try:
        p = os.path.join(store.data_dir(widget_id), "state.json")
        if os.path.exists(p):
            os.remove(p)
        store.forget(widget_id)
        _announce(widget_id, "wiped")
        return "wiped"
    except Exception as e:  # noqa: BLE001
        logger.warning(f"widgets.reset: no se pudo vaciar {widget_id}: {e}")
        return "error"


def _announce(widget_id: str, how: str, refresh: bool = True) -> None:
    """This path MUTATES widget data WITHOUT going through `store.save()` — and `save()` is the only point that
    announces "this widget changed". So deleting `state.json` was an INVISIBLE mutation: no event in the registry, no
    signal to the canvas, no line explaining it. Blind spot found firsthand (2026-08-10): another session had its
    results sheet emptied twice during a test and, with no reset trace, it looked like a widget persistence failure —
    a good while was spent looking for a bug that did not exist.

    It is announced through the SAME gate with two different purposes, both required:
      · `blank` → AUDIT row: which widget was emptied, how, and by whose order (`src`, provenance).
      · `data`  → signal listened to by the canvas (`sse.js` → `desktop.refreshData`), so the open card repaints NOW
        instead of continuing to show data that no longer exists on disk.
    Best-effort: emptying a widget must never fail because it could not be reported."""
    try:
        from voice.observer import emit
        from widgets.provenance import who
        src = who(widget_id)
        emit("widget", "blank", extra={"id": widget_id, "src": src, "how": how})
        if refresh:                                   # the path through `save()` has already emitted it
            emit("widget", "data", extra={"id": widget_id, "src": src})
    except Exception:
        pass


def blank_all() -> dict:
    """Leave BLANK the content of all widgets that do not declare their data belongs to the operator.

    Returns `{"blanked": [...], "kept": [...]}` — for the reset summary and so the operator can SEE what was respected
    (a list of kept items is the part that prevents surprise)."""
    blanked, kept = [], []
    for wid in _widget_ids():
        if not _has_state(wid):
            continue                       # nothing saved → nothing to empty (does not create files along the way)
        if is_durable(wid):
            kept.append(wid)
            continue
        how = _blank_one(wid)
        if how != "error":
            blanked.append(wid)
    if blanked or kept:
        logger.info(f"RESET widgets: en blanco {blanked or '—'} · conservados por declaración {kept or '—'}")
    return {"blanked": sorted(blanked), "kept": sorted(kept)}


def _widget_ids() -> list[str]:
    """Ids with saved data. Walk `widgets/_data/`, NOT the catalog: data for deleted widgets also remains there, and
    that is exactly what nobody would ever clean again."""
    out = []
    try:
        base = store.DATA_DIR
        for name in sorted(os.listdir(base)):
            if name.startswith("_") or not os.path.isdir(os.path.join(base, name)):
                continue
            out.append(name)
    except Exception:
        pass
    return out
