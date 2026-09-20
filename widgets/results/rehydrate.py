"""widgets/results/rehydrate.py — rebuild a results sheet from the task that produced it (V2-728).

Operator, 2026-09-20: *«si el usuario quiere ver cómo ha terminado, se va a esa lista, le da el botón y ve los
datos derivados»* — and, weeks later, *«de la tarea de buscar piso que te dije antes»*.

Neither was possible. A sheet lives under `widgets/_data/results--<id>/`, at most EIGHT of them are kept, and
`prune_sheets()` drops the oldest by FILE MTIME — so the ninth search deleted the first report, and the row
that still named it pointed at nothing. Since V2-728 the payload is copied onto the task when the errand ends
(`nucleo/tasks.kept_result`), which is what makes this file possible: the sheet is a VIEW and the task owns
the data, so a pruned sheet is a sheet that can be rebuilt rather than a report that is gone.

Nothing here decides WHICH task. That is the caller's question and it has its own answer
(`memory.tasks_store.task_search` narrows without a model, `nucleo/jev.py::select_many` chooses); this only
puts the chosen one back on screen.
"""
from __future__ import annotations

from . import lifecycle as _lifecycle
from .sheet_names import instance_id, sheet_key
from widgets import store

#: Slots written back onto the sheet, in the order `view_data` expects to find them. `result` carries the
#: sheet minus the three below (see `kept_result`), so it is spread first and they are laid on top.
_SLOTS = ("criteria", "sources", "process")


def sheet_from_task(task_id: str) -> dict:
    """Put a finished task's report back on disk under its own sheet. Returns what the canvas needs to show it.

    `{"ok": True, "instance": "results::<id>", "title": …, "rebuilt": bool}` — `rebuilt` says whether the
    sheet had to be recreated or was still there, because those are different answers to «is this still the
    report I saw» and the caller may want to say so.

    IDEMPOTENT and non-destructive: a sheet that still exists is left exactly as it is. Overwriting it with
    the snapshot would discard anything added since the errand closed, which is the «error de borrar
    búsquedas» this whole lineage exists to remove.
    """
    tid = str(task_id or "").strip()
    if not tid:
        return {"ok": False, "error": "sin tarea"}
    if store.exists(sheet_key(tid)):
        data = _lifecycle.view_data(tid)
        return {"ok": True, "instance": instance_id(tid), "rebuilt": False,
                "title": str(data.get("title") or "")}
    from nucleo import tasks as _tasks
    parts = _tasks.artifacts(tid)
    if not parts.get("result"):
        # Nothing was ever kept for this task: an errand with no sheet, or one that closed before V2-728.
        # Saying so is the point — an empty sheet would look like a report that came back with nothing.
        return {"ok": False, "error": "esta tarea no guardó resultados"}
    data = dict(parts["result"])
    for slot in _SLOTS:
        if parts.get(slot):
            data[slot] = parts[slot]
    data.pop("tab", None)            # the tab he was on belonged to the session that is over
    data.pop("view", None)
    data.pop("focus", None)
    _lifecycle._save(data, tid)
    return {"ok": True, "instance": instance_id(tid), "rebuilt": True,
            "title": str(data.get("title") or "")}


def has_results(task_id: str) -> bool:
    """Is there anything to reopen? What the «Hechas» row's button keys off — a button that opens nothing is
    worse than no button, and this is the one question that decides whether to draw it."""
    tid = str(task_id or "").strip()
    if not tid:
        return False
    if store.exists(sheet_key(tid)):
        return True
    from nucleo import tasks as _tasks
    return bool(_tasks.artifact(tid, "result"))
