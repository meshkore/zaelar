"""widgets/agenda/tasklists.py — the operator's OWN tasks, in numbered lists (V2-744).

A general task list plus lists he makes for anything («la lista de la compra»), each with an id he can later share
with another agent over MeshKore. From V2-744 «tarea» means HIS; the assistant's own work is a PROCESS (job).

## Three decisions worth writing down

**ONE array, not two.** A list item and a planner task share `db["tasks"]`; a task carries the `listId` it hangs
from. A second array would be two writers of one fact (`system_tasks.py`: «THE AGENDA READS, IT DOES NOT DUPLICATE»).

**The planner places only what says how long it takes** — a duration, an hour or a project; it never invents
30 minutes for «pan» (V2-652: a missing fact is a fact, not a slot for a default).

**The NUMBER is the screen position, and nothing else.** `no` is derived on every read («abre la lista número 3»),
and the brain's digest is built from the same function the render is (the `index.py` lesson).

The list ID is a readable slug (`tl_la_compra`): a human can read it aloud to hand it to another agent.
"""
from __future__ import annotations

import re
import time

from .when import _strip_accents, _resolve_date, _resolve_time, _today
from widgets.agenda import task_read as _task_read  # split out (refactor2710-99)


#: Every action this module owns. `data.apply_action` delegates the whole set in one branch — the four
#: planner verbs included, because «done» on a shopping item and «done» on a project task are the same verb
#: and splitting them across two files is how they would drift.
ACTIONS = ("add_task", "update_task", "delete_task", "done", "drop", "snooze", "not_now",
           "add_list", "rename_list", "clear_list", "delete_list", "show_tasks", "restore")


# ── reading ────────────────────────────────────────────────────────────────────────────────────────────


#: How many removals the trash remembers. Operator, 2026-09-21: *«otra cosa es que guardes un rastro de lo
#: que habia, por si me he equivocado, y te digo restauralo»*. Bounded because this rides in the agenda's own
#: store and an unbounded undo log is a store that grows for ever; twenty is more removals than a voice
#: session makes, and the oldest one falling off is the only thing that can be lost.
TRASH_MAX = 20


def _to_trash(db: dict, kind: str, rows: list, label: str, list_row: dict | None = None) -> None:
    """Remember what a removal is ABOUT TO take, so «restauralo» has something to bring back.

    ⚠️ Called BEFORE the rows leave `db["tasks"]`: it reads the store to learn each row's slot, and after the
    filter there is no slot left to read. Written the other way round first, and every restore then appended
    to the bottom of the list — the data came back and the numbering did not.

    The rows are stored VERBATIM — same ids, same listId, same status — because a restore that rebuilds a
    task from its title is a new task wearing the old one's name, and the number he reads would move. The
    list record travels with a `delete_list` for the same reason: putting three orphan tasks back into
    «General» is not what he asked to undo."""
    if not rows and not list_row:
        return
    # The POSITION travels with the row, not just the row. `items()` numbers by store order, so a restore
    # that appends puts «la 1» back as «la 4» — and the number is the whole way he addresses a task («borra
    # el item 2»). Undoing a removal has to give him back the screen he had, not merely the data.
    order = {id(r): i for i, r in enumerate(db.get("tasks", []) or [])}
    entry = {"at": time.time(), "kind": kind, "label": str(label or ""),
             "tasks": [dict(r, _pos=order.get(id(r), 10 ** 6)) for r in rows]}
    if list_row:
        entry["list"] = dict(list_row)
    bin_ = db.setdefault("trash", [])
    bin_.append(entry)
    del bin_[:-TRASH_MAX]


# ── resolving what he NAMED ────────────────────────────────────────────────────────────────────────────


# ── writing ────────────────────────────────────────────────────────────────────────────────────────────

def apply(action: str, payload: dict, db: dict) -> dict:
    """Run one task/list action against `db` IN PLACE. Returns `{ok: True, …}` or a refusal the model can
    act on; the caller persists only on success. Never raises."""
    p = payload or {}
    act = str(action or "")

    if act == "add_list":
        name = str(p.get("name") or p.get("list") or p.get("title") or "").strip()
        if not name:
            return {"ok": False, "error": "la lista no lleva nombre — vuelve a llamar a add_list con `name` "
                                          "(«la compra», «casa», «viaje a Roma»); NO inventes uno"}
        _task_read.migrate(db)                                   # …before reading the array: it may create it
        if any(_task_read._norm(l.get("name")) == _task_read._norm(name) for l in db["taskLists"]):
            hit = next(l for l in _task_read.lists(db) if _task_read._norm(l["name"]) == _task_read._norm(name))
            return {"ok": True, "list": hit["id"], "listNo": hit["no"], "existed": True}
        lid = _task_read._slug(name, "tl_") or f"tl_{int(time.time()) % 1000000}"
        taken = {str(l.get("id")) for l in db["taskLists"]}
        if lid in taken:
            lid = f"{lid}_{int(time.time()) % 100000}"
        db["taskLists"].append({"id": lid, "name": name, "createdAt": _today()})
        return {"ok": True, "list": lid, "listNo": len(db["taskLists"]), "created": True}

    if act in ("rename_list", "clear_list", "delete_list"):
        raw = p.get("list") or p.get("name") or p.get("listId")
        # An EMPTY selector never means «the one on screen» when the verb removes things. `pick_list`
        # falls back to the current list by design — right for «añade pan», wrong for «vacíala», where the
        # fallback would empty whatever happened to be open. `contract.guard` refuses this one turn earlier
        # through the manifest's `ref`; this is the same rule next to the write, where it cannot be bypassed.
        if act != "rename_list" and not str(raw or "").strip():
            return {"ok": False, "error": f"dime QUÉ lista: su número o su nombre — {act} no vacía «la de "
                                          f"ahora», tienes {_task_read._names(_task_read.lists(db))}"}
        lst, why = _task_read.pick_list(db, raw)
        if not lst:
            return {"ok": False, "error": why}
        if act == "rename_list":
            new = str(p.get("newName") or p.get("new_name") or p.get("title") or "").strip()
            if not new:
                return {"ok": False, "error": "no me ha llegado el nombre nuevo — llama a rename_list con "
                                              "`list` y `newName`"}
            for l in db.get("taskLists", []):
                if str(l.get("id")) == lst["id"]:
                    l["name"] = new
            return {"ok": True, "list": lst["id"], "renamed": new}
        rows = [t for t in db.get("tasks", []) if str(t.get("listId") or "") == lst["id"]]
        gone = next((dict(l) for l in db.get("taskLists", []) if str(l.get("id")) == lst["id"]), None)
        _to_trash(db, act, rows, lst["name"], list_row=(gone if act == "delete_list" else None))
        db["tasks"] = [t for t in db.get("tasks", []) if str(t.get("listId") or "") != lst["id"]]
        if act == "clear_list":
            return {"ok": True, "list": lst["id"], "cleared": len(rows), "undo": True}
        # The GENERAL list is not deletable — it is where a task with no home lands, and deleting it would
        # leave the next `add_task` writing into a list that does not exist. Emptying it is `clear_list`.
        if lst["id"] == _task_read.GENERAL:
            return {"ok": True, "list": _task_read.GENERAL, "cleared": len(rows), "kept_list": True, "undo": True}
        db["taskLists"] = [l for l in db.get("taskLists", []) if str(l.get("id")) != lst["id"]]
        return {"ok": True, "list": lst["id"], "deleted_list": True, "cleared": len(rows), "undo": True}

    if act == "show_tasks":
        lst, why = _task_read.pick_list(db, p.get("list") or p.get("name") or p.get("listId"))
        if not lst:
            return {"ok": False, "error": why}
        db["tasksView"] = {"list": lst["id"], "n": int((db.get("tasksView") or {}).get("n", 0)) + 1,
                           "at": time.time()}
        return {"ok": True, "list": lst["id"], "listNo": lst["no"]}

    if act == "add_task":
        title = str(p.get("title") or p.get("task") or p.get("item") or "").strip()
        if not title:
            return {"ok": False,
                    "error": "no me ha llegado la tarea — vuelve a llamar a add_task con `title` (y `list` "
                             "si va a una lista suya, `date`/`time` si tiene día u hora)"}
        lst, why = _task_read.pick_list(db, p.get("list") or p.get("listId"))
        if not lst:
            return {"ok": False, "error": why}
        _task_read.migrate(db)
        tid = _task_read._slug(title, "t_") or f"t_{int(time.time()) % 1000000}"
        if any(t.get("id") == tid for t in db.get("tasks", [])):
            tid = f"{tid}_{int(time.time()) % 100000}"     # same slug twice is a second task, not a lost write
        t = {"id": tid, "title": title, "status": "todo", "listId": lst["id"], "createdAt": _today()}
        _task_read._details(t, p)
        db.setdefault("tasks", []).append(t)
        # V2-769 — `revert` names the call that takes this row back out: the turn layer runs it when the
        # whole sentence arrives and this write turns out to have come from a piece of it.
        return {"ok": True, "task": tid, "list": lst["id"], "no": len(_task_read.items(db, lst["id"])),
                "revert": {"action": "delete_task", "payload": {"taskId": tid}}}

    if act in ("update_task", "delete_task", "done", "drop", "snooze", "not_now"):
        lst, why = _task_read.pick_list(db, p.get("list") or p.get("listId"))
        if not lst:
            return {"ok": False, "error": why}
        tid = str(p.get("taskId") or "").strip()
        t = _task_read._raw_task(db, tid) if tid else None
        if t is None:
            t, why = _task_read.pick_task(db, lst, p.get("task") or p.get("item") or p.get("title") or tid)
            if t is None:
                return {"ok": False, "error": why}
        if act == "delete_task":
            # The removal is DIRECT and it is remembered — the two halves of the operator's rule of
            # 2026-09-21 («cuando digo borrar esto, lo borras sin preguntar (...) otra cosa es que guardes un
            # rastro de lo que habia»). Nothing here asks him anything; `restore` is what answers a mistake.
            _to_trash(db, "delete_task", [t], str(t.get("title") or ""))
            db["tasks"] = [x for x in db.get("tasks", []) if x.get("id") != t["id"]]
            return {"ok": True, "task": t["id"], "deleted": str(t.get("title") or ""), "undo": True}
        if act == "done":
            t["status"] = "done"
            t["updatedAt"] = _today()
        elif act == "drop":
            t["status"] = "dropped"
        elif act == "snooze":
            t["snoozedUntil"] = _today()
        elif act == "not_now":
            t["avoidance"] = int(t.get("avoidance", 0)) + 1     # coaching signal, not a removal
        else:
            new = str(p.get("newTitle") or p.get("new_title") or "").strip()
            if new:
                t["title"] = new
            moved = p.get("newList") or p.get("new_list") or p.get("toList")
            if moved:
                dest, why = _task_read.pick_list(db, moved)
                if not dest:
                    return {"ok": False, "error": why}
                t["listId"] = dest["id"]
            st = _task_read._norm(p.get("status"))
            if st:
                t["status"] = ("done" if ("hech" in st or "done" in st or "complet" in st)
                               else "todo" if ("pend" in st or "todo" in st or "sin" in st)
                               else t.get("status", "todo"))
            _task_read._details(t, p)
        return {"ok": True, "task": t["id"], "list": str(t.get("listId") or _task_read.GENERAL)}

    if act == "restore":
        # «Restauralo» / «deshaz eso» — the other half of a removal that no longer asks. With no argument it
        # undoes the LAST one, which is the shape the mistake takes: he deletes, he sees it go, he says put
        # it back. A `what` narrows it to the most recent removal whose label he names, for the case where
        # two removals happened before he noticed.
        bin_ = db.get("trash") or []
        if not bin_:
            return {"ok": False, "error": "no tengo nada en la papelera de tareas — no he borrado nada que "
                                          "pueda devolver"}
        want = _task_read._norm(p.get("what") or p.get("task") or p.get("list") or p.get("title") or "")
        idx = len(bin_) - 1
        if want:
            hits = [i for i, e in enumerate(bin_) if want in _task_read._norm(e.get("label"))]
            if not hits:
                return {"ok": False,
                        "error": "en la papelera no tengo nada que se llame asi; lo ultimo que borre fue "
                                 f"«{bin_[-1].get('label')}»"}
            idx = hits[-1]
        entry = bin_.pop(idx)
        _task_read.migrate(db)
        # The list comes back FIRST when it went: its tasks carry its id and would otherwise be migrated
        # into General by the very next read (see `migrate` — a task whose list does not exist is homeless).
        row = entry.get("list")
        if isinstance(row, dict) and not any(str(l.get("id")) == str(row.get("id"))
                                             for l in db.get("taskLists", [])):
            db.setdefault("taskLists", []).append(dict(row))
        known = {str(t.get("id")) for t in db.get("tasks", [])}
        back = [t for t in (entry.get("tasks") or []) if str(t.get("id")) not in known]
        rows_ = db.setdefault("tasks", [])
        # `_pos` of the FIRST row is 0, and `x or default` reads 0 as absent — the restore then appended
        # every undo to the bottom of the list while the slot was sitting right there in the trash entry.
        def _slot(r, _n=None):
            v = r.get("_pos")
            return int(v) if isinstance(v, int) else 10 ** 6
        for t in sorted(back, key=_slot):
            row_ = {k: v for k, v in t.items() if k != "_pos"}
            rows_.insert(min(_slot(t), len(rows_)), row_)
        return {"ok": True, "restored": len(back), "label": entry.get("label") or "",
                "what": entry.get("kind") or "", "list": str(row.get("id")) if isinstance(row, dict) else ""}

    return {"ok": False, "error": f"la agenda no sabe hacer «{act}» con una tarea"}


# ── what the brain reads ───────────────────────────────────────────────────────────────────────────────


