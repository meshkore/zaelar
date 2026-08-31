"""widgets/results/lifecycle.py — the ERRAND's three gates on the sheet: it OPENS it, NAMES it and CLOSES it.

Extracted from `data.py` on 2026-08-31 (V2-530) because the architecture ratchet asked for a module instead of a
higher ceiling, and the cut was already drawn in the comment these gates carried: they are NOT actions of
`apply_action`'s vocabulary — nobody asks for them from a prompt, the errand's LIFECYCLE fires them, and putting
them in that vocabulary would put them within a worker's reach, which is exactly who must not decide when the
sheet is opened, renamed or closed.

Everything here writes through `data`'s own store seams (`_empty` / `view_data` / `_save` / `_clip`), so the sheet
has a single writer as it always did. `data.py` re-exports the three names: no caller changed.
"""
from __future__ import annotations

from widgets.results.live import _clean_phases

# The sheet's STORE layer (`view_data` / `_save` / `_empty` / `_clip`) still lives in `data.py`, and `data.py`
# re-exports these three gates, so the import has to be late or the two modules would deadlock at import time.
# Naming the debt rather than hiding it: the cycle disappears the day that store layer becomes its own module,
# which is a bigger cut than the ratchet was asking for tonight.


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


# ── THE ERRAND OPENS AND CLOSES THE SHEET (V2-227 scope C) ───────────────────────────────────────────────────
# The only two gates the dispatcher uses so the operator can SEE the work as it happens. They are not actions
# in `apply_action`'s vocabulary: nobody asks for them from a prompt; the errand's lifecycle triggers them —
# putting them there would place them within a worker's reach, and that is exactly who must not decide when the
# sheet is opened.

def begin_task(title: str = "", fresh: bool = True, sheet: str = "") -> dict:
    """The errand has just started: the sheet opens in PROCESS, with nothing inside yet.

    `fresh` OPENS the sheet (title = what the operator requested, with no results or history from the previous
    search). It is turned off when another errand is still writing here: clearing it then would erase what that
    errand had already delivered, and the sheet is unique until C4 ("two searches = two sheets") exists.

    In both cases the PERSISTED tab is removed. That is what makes the sheet open in Process: `data.tab` takes
    precedence over the derived state —and it should, since it is where the operator chose to look— but that
    decision belonged to the PREVIOUS errand, and carrying it over would leave the operator looking at an empty
    list while the story unfolds in the one next to it.
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
    """Change ONLY this sheet's name, leaving everything it holds alone (V2-530).

    Separate from `begin_task` because that one OPENS the sheet — it is the errand's opening gesture and it wipes items,
    tabs and process. Renaming happens later, on a sheet the operator is already looking at, once the errand's
    title has been composed; reusing `begin_task(fresh=True)` for it would erase the very results it is naming.
    """
    t = " ".join(str(title or "").split())
    if not t:
        return {"ok": False, "error": "sin título"}
    data = view_data(sheet)
    data["title"] = _clip(t, "sheet_title")
    _save(data, sheet)
    return {"ok": True, "title": data["title"]}


def end_task(phases, sheet: str = "") -> dict:
    """The errand is over: its story is saved with the report and the loader is stopped.

    It is PERSISTED because the sheet is: a report survives a restart, and its explanation of how it was reached
    has to survive with it. The write is also what TURNS OFF the loader — the phase emitter only fires when a phase
    CHANGES, so without this save the card would keep saying «Trabajando…» about a worker that no longer exists.
    """
    lines = _clean_phases(phases)
    data = {k: v for k, v in view_data(sheet).items() if k not in ("counts", "progress")}
    if lines:
        data["process"] = lines
    else:
        data.pop("process", None)            # without a single phase there is no story to tell; none is invented
    # …and its NUMBERS with it (V2-296). `view_data` has just derived them from the live record, which will cease to
    # exist in an instant: if they are not saved here, the report is left without the tally of what it took to reach it.
    if not isinstance(data.get("harvest"), dict) or not any((data.get("harvest") or {}).values()):
        data.pop("harvest", None)            # without a single number there is no tally to give; zeros are not saved
    _save(data, sheet)
    return {"ok": True, "phases": len(lines)}
