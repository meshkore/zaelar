"""Sheet NAMING and housekeeping for the results widget (V2-259 · V2-439).

Extracted from `data.py` on the 2026-09-05 ratchet pass (the file had grown past its ceiling; the ratchet asks
for a module, never a taller ceiling). Same move and gesture as `live.py`/`lifecycle.py`: `data.py` re-exports
every name, so callers keep saying `data.sheet_key` and the tests keep patching `store` where the code looks.
"""
from __future__ import annotations

from .. import store

WIDGET_ID = "results"

# ── ONE SHEET PER TASK (V2-259) ──────────────────────────────────────────────────────────────────────────────
# The operator's literal request: «si tenemos un widget de results abierto, búsqueda terminada, y lanzamos otra,
# se abre un widget nuevo. Con esta regla no cometeremos errores de borrar búsquedas». The deletion they feared was
# IN THE CODE: `begin_task(fresh=True)` opened a new sheet —new title, without results or history— as soon as the
# next task arrived. With instances, OPENING no longer means DELETING: a new sheet is a new key and the previous one
# remains where it was.
#
# The instance is the TASK, not the browser. Two browsers for the same task land on the same sheet (V2-257:
# the sheet stores findings regardless of which browser they came from); two tasks are two sheets.
#
# The EMPTY key remains plain `results`, deliberately: it is the sheet already on disk, so nothing needs migrating
# and no orphan lineage competes with another (the V2-242 trap, where `weather:soria` and
# `meteo-soria:weather:soria` coexisted with `valid=1`). What must be watched —and has a test— is that no WRITER
# remains unaware of its sheet: it would write to nobody's while the operator watches theirs.
_INSTANCE_SEP = "--"          # `widgets/store._safe_id` allows only [A-Za-z0-9_-]: «::» would not survive on disk
_MAX_SHEETS = 8               # limit on stored instantiated sheets; see `prune_sheets()`


def _safe_sheet(sheet) -> str:
    return "".join(c for c in str(sheet or "").strip() if c.isalnum() or c in "-_")[:64]


def sheet_key(sheet: str = "") -> str:
    """Storage key for ONE sheet. Without an instance → the default one, byte for byte. `results::X` IS `X`."""
    s = _safe_sheet(str(sheet or "").removeprefix(f"{WIDGET_ID}::"))   # V2-439: sin esto la clave NO existe
    return WIDGET_ID if not s else f"{WIDGET_ID}{_INSTANCE_SEP}{s}"


def sheets() -> list[str]:
    """The sheets that EXIST on disk, the default first and instantiated ones in write order (the most recent last).
    This deliberately reads from storage rather than an in-memory list: the sheet persists across restarts (V2-233),
    while a RAM list would say «there are none» immediately after startup."""
    out: list[str] = []
    try:
        import os
        base = store.DATA_DIR
        pref = WIDGET_ID + _INSTANCE_SEP
        rows = []
        for name in os.listdir(base):
            if not name.startswith(pref):
                continue
            f = os.path.join(base, name, "state.json")
            if os.path.exists(f):
                rows.append((os.path.getmtime(f), name[len(pref):]))
        rows.sort()
        out = [sid for _, sid in rows]
    except Exception:  # noqa: BLE001
        return [""] if store.exists(WIDGET_ID) else []
    if store.exists(WIDGET_ID):
        out.insert(0, "")
    return out


def prune_sheets(keep: int = _MAX_SHEETS) -> int:
    """Limit on stored sheets. The sheet PERSISTS deliberately, so N instances would grow without end; the `keep`
    most recent and the default sheet are retained (it belongs to no task, so nobody should delete it).
    Returns how many were discarded, so pruning can be COUNTED instead of discovered later."""
    inst = [s for s in sheets() if s]
    dropped = 0
    for sid in inst[:max(0, len(inst) - max(1, keep))]:
        try:
            if store.delete(sheet_key(sid)):
                dropped += 1
        except Exception:  # noqa: BLE001
            pass
    return dropped


def instance_id(sheet: str = "") -> str:
    """CARD ID on the canvas (`results::<corr>`), which uses «::» —the canvas separator, not the disk separator."""
    s = _safe_sheet(sheet)
    return WIDGET_ID if not s else f"{WIDGET_ID}::{s}"
