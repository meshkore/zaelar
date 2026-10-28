"""widgets/results/lifecycle.py — the ERRAND's three gates on the sheet: it OPENS it, NAMES it and CLOSES it (V2-530).

They are NOT `apply_action` vocabulary: the errand's LIFECYCLE fires them, and a worker must not decide when the
sheet opens, is renamed or closes. Everything writes through `data`'s store seams, so the sheet keeps one writer.
"""
from __future__ import annotations

from widgets.results.live import _clean_phases

# The STORE layer lives in `data.py`, which re-exports these gates: the import is late or the two would deadlock.


def _empty():
    from . import data as _d
    return _d._empty()


def _save(data, sheet=""):
    from . import data as _d
    return _d._save(data, sheet)


def view_data(sheet: str = "") -> dict:
    from . import data as _d
    return _d.view_data(sheet)


def _clip(text, key: str) -> str:
    from . import data as _d
    return _d._clip(text, key)


# ── THE ERRAND OPENS AND CLOSES THE SHEET (V2-227 scope C) — so the operator can SEE the work as it happens.

def begin_task(title: str = "", fresh: bool = True, sheet: str = "") -> dict:
    """The errand has just started: the sheet opens with nothing inside yet. `fresh` wipes it (title = the request);
    off when another errand still writes here. The persisted tab, view and story always go: they were the last errand's.
    """
    data = _empty() if fresh else view_data(sheet)
    if fresh:
        t = " ".join(str(title or "").split())
        if t:
            data["title"] = _clip(t, "sheet_title")
    else:
        data = {k: v for k, v in data.items() if k not in ("counts", "progress")}
    data.pop("tab", None)
    data.pop("view", None)                   # the open detail belonged to a result from the previous errand
    data.pop("focus", None)
    data.pop("process", None)                # the story that follows belongs to THIS errand
    data.pop("harvest", None)                # …and so do its numbers (V2-296)
    _save(data, sheet)
    return {"ok": True, "fresh": bool(fresh), "title": data.get("title", "")}


def rename_task(title: str, sheet: str = "") -> dict:
    """Change ONLY this sheet's name (V2-530) — `begin_task(fresh=True)` would erase the results it is naming."""
    t = " ".join(str(title or "").split())
    if not t:
        return {"ok": False, "error": "sin título"}
    data = view_data(sheet)
    data["title"] = _clip(t, "sheet_title")
    _save(data, sheet)
    return {"ok": True, "title": data["title"]}


def end_task(phases, sheet: str = "") -> dict:
    """The errand is over: its story and numbers are PERSISTED with the report, and the save turns the loader off."""
    lines = _clean_phases(phases)
    data = {k: v for k, v in view_data(sheet).items() if k not in ("counts", "progress")}
    if lines:
        data["process"] = lines
    else:
        data.pop("process", None)            # without a single phase there is no story to tell; none is invented
    # …and its NUMBERS (V2-296): derived from a live record that is about to cease to exist.
    if not isinstance(data.get("harvest"), dict) or not any((data.get("harvest") or {}).values()):
        data.pop("harvest", None)            # without a single number there is no tally to give; zeros are not saved
    _save(data, sheet)
    return {"ok": True, "phases": len(lines)}
