"""widgets/agenda/tasklists.py — the operator's OWN tasks, in numbered lists (V2-744).

Operator, 2026-09-21: *«el widget de la agenda va a albergar tareas y agenda… quiero que haya una lista
general de tareas y luego que el usuario pueda generar una lista para varias cosas… podemos generar una
lista de la compra y eso tendrá un identificador y ese identificador lo podré compartir en el futuro con
otro agente a través de la red de MeshKore»*. And the rule that governs the whole batch, in his words:
*«a las tareas que yo hago las llamo procesos (jobs en inglés) y las separo de las tareas personales del
operador que van en su agenda»* — so from V2-744 «tarea» means THIS, and the assistant's own work is a
PROCESS everywhere the operator can read it.

## Three decisions worth writing down

**ONE array, not two.** A list item and a planner task are both «something the operator has to do», so they
share `db["tasks"]` and a task simply carries the `listId` it hangs from. The alternative — a second array
for the new section — is the two-writers-of-one-fact defect this widget already has a monument to (see
`system_tasks.py`: «THE AGENDA READS, IT DOES NOT DUPLICATE»), and it would have shown up the first time
«márcame hecha la compra» found the row in the wrong table.

**The planner places only what says how long it takes.** The day planner turns a task into a block of time,
and until now it invented `estimateMinutes: 30` for anything without one. With a shopping list in the same
array that invention would fill the operator's working day with half-hour blocks called «pan» — so a task is
plannable only when it carries a duration, an hour or a project. That is not a special case for lists: it is
the V2-652 rule («a missing fact is a fact, not a slot for a default») applied to the one field the planner
cannot work without.

**The NUMBER is the screen position, and nothing else.** He asked for numbering so he can say «abre la lista
número 3, coge el ítem número 2 y modifícalo». A stored, stable number would drift from what he is reading
the moment anything is deleted — and the number only exists to point at the screen. So `no` is derived on
every read, and the digest the brain sees is built from the same function the render is, which is the
`index.py` lesson (two views of one card that disagreed about what «next» meant).

The list ID is a readable slug (`tl_la_compra`), not a random hex: it is the thing he will hand to another
agent over the MeshKore cluster, and an identifier a human can read aloud survives that trip.
"""
from __future__ import annotations

import re
import time

from .when import _strip_accents, _resolve_date, _resolve_time, _today

#: The built-in list every task without a home belongs to. Its NAME is stored so the operator can rename it
#: like any other; the widget translates the untouched default, which is the same word in both languages.
GENERAL = "general"
GENERAL_NAME = "General"

#: Every action this module owns. `data.apply_action` delegates the whole set in one branch — the four
#: planner verbs included, because «done» on a shopping item and «done» on a project task are the same verb
#: and splitting them across two files is how they would drift.
ACTIONS = ("add_task", "update_task", "delete_task", "done", "drop", "snooze", "not_now",
           "add_list", "rename_list", "clear_list", "delete_list", "show_tasks")

#: How long a pushed tasks view stays worth obeying — the same TTL and the same reason as `data._VIEW_TTL_S`:
#: «ábreme la lista de la compra» then `show_widget` has to arrive already pointing at it, and a push kept
#: for ever would yank the list he is reading a week later.
_VIEW_TTL_S = 600

_LIVE = (None, "todo", "in_progress")


# ── reading ────────────────────────────────────────────────────────────────────────────────────────────

def migrate(db: dict) -> dict:
    """Give every task a home. Runs on the lazy store migration (agenda DB v1 → v2) and, defensively, on
    every read of the lists: a task written by an older build has no `listId` and would be invisible in a
    section built around them, which is data loss wearing the face of an empty screen."""
    lists = db.get("taskLists")
    if not isinstance(lists, list) or not lists:
        lists = [{"id": GENERAL, "name": GENERAL_NAME, "builtin": True, "createdAt": _today()}]
        db["taskLists"] = lists
    known = {str(l.get("id") or "") for l in lists}
    for t in db.get("tasks", []) or []:
        if str(t.get("listId") or "") not in known:
            t["listId"] = GENERAL
    return db


def plannable(t: dict) -> bool:
    """Can the day planner place this task? Only when the task itself says how long it takes, when it
    happens, or which project it advances. See the module header: the planner's 30-minute default was an
    invented fact, and with checklist items in the same array it became a visible one."""
    return bool(t.get("estimateMinutes") or t.get("startTime") or t.get("projectId"))


def lists(db: dict) -> list[dict]:
    """The lists in screen order, each with its number and its progress. `no` is derived — see the header."""
    migrate(db)
    out = []
    for i, l in enumerate(db.get("taskLists", [])):
        lid = str(l.get("id") or "")
        rows = [t for t in db.get("tasks", []) if str(t.get("listId") or "") == lid
                and t.get("status") != "dropped"]
        out.append({"id": lid, "name": str(l.get("name") or lid), "no": i + 1,
                    "builtin": bool(l.get("builtin")),
                    "total": len(rows), "done": len([t for t in rows if t.get("status") == "done"])})
    return out


def items(db: dict, list_id: str) -> list[dict]:
    """One list's tasks in screen order, numbered the same way the render numbers them."""
    migrate(db)
    lid = str(list_id or GENERAL)
    out = []
    for t in db.get("tasks", []):
        if str(t.get("listId") or "") != lid or t.get("status") == "dropped":
            continue
        out.append({"id": t["id"], "no": len(out) + 1, "title": str(t.get("title") or ""),
                    "status": str(t.get("status") or "todo"),
                    "date": str(t.get("date") or ""), "time": str(t.get("startTime") or ""),
                    "planned": plannable(t)})
    return out


def view(db: dict) -> dict:
    """What the render needs for the whole TAREAS section: the lists and every list's items. Everything at
    once because a widget cannot fetch (the house rule) — switching list has to be client-side."""
    ls = lists(db)
    return {"lists": ls, "items": {l["id"]: items(db, l["id"]) for l in ls},
            "view": fresh_view(db)}


def fresh_view(db: dict) -> dict | None:
    v = db.get("tasksView") or None
    if not v:
        return None
    at = float(v.get("at") or 0)
    return v if at and (time.time() - at) <= _VIEW_TTL_S else None


# ── resolving what he NAMED ────────────────────────────────────────────────────────────────────────────

_FILLER = {"lista", "list", "la", "el", "los", "las", "numero", "número", "number", "num", "n",
           "item", "ítem", "tarea", "task", "the", "de", "of", "mi", "my"}
_ORD = {"primera": 1, "primero": 1, "uno": 1, "una": 1, "first": 1,
        "segunda": 2, "segundo": 2, "dos": 2, "second": 2,
        "tercera": 3, "tercero": 3, "tres": 3, "third": 3,
        "cuarta": 4, "cuarto": 4, "cuatro": 4, "fourth": 4,
        "quinta": 5, "quinto": 5, "cinco": 5, "fifth": 5,
        "sexta": 6, "sexto": 6, "seis": 6, "sixth": 6,
        "septima": 7, "septimo": 7, "siete": 7, "seventh": 7,
        "octava": 8, "octavo": 8, "ocho": 8, "eighth": 8,
        "novena": 9, "noveno": 9, "nueve": 9, "ninth": 9,
        "decima": 10, "decimo": 10, "diez": 10, "tenth": 10}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9ñ ]+", " ", _strip_accents(str(s or "")).lower())).strip()


def number_in(raw) -> int | None:
    """The ORDINAL he spoke, or None when he named a thing instead of a position.

    Only when what is left after the filler words IS the number: «la lista 3» and «el ítem segundo» are
    positions, «comprar 2 barras de pan» is a title with a digit in it, and reading that as «item 2» would
    act on a row he never mentioned."""
    toks = [t for t in _norm(raw).split() if t and t not in _FILLER and t != "#"]
    if len(toks) != 1:
        return None
    t = toks[0].lstrip("#")
    if t.isdigit():
        return int(t) or None
    return _ORD.get(t)


def _match(rows: list[dict], raw: str, key: str) -> tuple[dict | None, list[dict]]:
    """Exact → prefix → substring → token overlap. Returns (hit, candidates) and NEVER guesses between two:
    an ambiguity comes back as candidates so the caller can ask, which is `widgets/refs.py`'s own rule."""
    want = _norm(raw)
    if not want:
        return None, []
    exact = [r for r in rows if _norm(r.get(key)) == want]
    if len(exact) == 1:
        return exact[0], []
    pre = [r for r in rows if _norm(r.get(key)).startswith(want)]
    if len(pre) == 1:
        return pre[0], []
    sub = [r for r in rows if want in _norm(r.get(key))]
    if len(sub) == 1:
        return sub[0], []
    if sub:
        return None, sub
    wt = set(want.split())
    ov = [r for r in rows if wt & set(_norm(r.get(key)).split())]
    return (ov[0], []) if len(ov) == 1 else (None, ov)


def pick_list(db: dict, raw) -> tuple[dict | None, str]:
    """Which list he means: a number, a name, or —said nothing— the one on screen, else General."""
    ls = lists(db)
    s = str(raw or "").strip()
    if not s:
        cur = (fresh_view(db) or {}).get("list") or GENERAL
        return next((l for l in ls if l["id"] == cur), ls[0]), ""
    n = number_in(s)
    if n is not None:
        hit = next((l for l in ls if l["no"] == n), None)
        return (hit, "") if hit else (None, f"no tienes ninguna lista número {n} — tienes "
                                             f"{len(ls)}: {_names(ls)}")
    hit = next((l for l in ls if l["id"] == _slug(s)), None)
    if hit:
        return hit, ""
    hit, cands = _match(ls, s, "name")
    if hit:
        return hit, ""
    if cands:
        return None, "¿cuál de estas listas? " + _names(cands)
    return None, f"no encuentro esa lista — tienes {_names(ls)}"


def pick_task(db: dict, lst: dict, raw) -> tuple[dict | None, str]:
    """Which task he means, INSIDE the list he named — and, failing that, anywhere.

    The list is tried first on purpose: «borra el 2» while the shopping list is open means the second row of
    the shopping list, and a search across every list would make the same sentence mean different things
    depending on how many tasks exist elsewhere."""
    s = str(raw or "").strip()
    if not s:
        return None, "dime cuál: su número en la lista o su nombre"
    # …and it may already BE the id. `widgets/refs.py` resolves the operator's spoken reference against
    # `ref_index()` and writes the id it found into the key the manifest's `ref` names — which is `task` for
    # these actions. Matching it as a title would then fail on the one path that had already done the work.
    hit = _raw_task(db, s)
    if hit is not None:
        return hit, ""
    rows = items(db, lst["id"])
    n = number_in(s)
    if n is not None:
        hit = next((r for r in rows if r["no"] == n), None)
        if not hit:
            return None, (f"la lista «{lst['name']}» no tiene un ítem número {n} — tiene {len(rows)}"
                          + (": " + _titles(rows) if rows else ""))
        return _raw_task(db, hit["id"]), ""
    hit, cands = _match(rows, s, "title")
    if not hit and not cands:
        allrows = [r for l in lists(db) for r in items(db, l["id"])]
        hit, cands = _match(allrows, s, "title")
    if hit:
        return _raw_task(db, hit["id"]), ""
    if cands:
        return None, "¿cuál de estas? " + _titles(cands)
    return None, f"no encuentro esa tarea en «{lst['name']}»" + (": " + _titles(rows) if rows else "")


def _raw_task(db: dict, tid: str) -> dict | None:
    return next((t for t in db.get("tasks", []) if t.get("id") == tid), None)


def _names(ls) -> str:
    return "; ".join(f"{l['no']}. {l['name']}" for l in ls[:8])


def _titles(rows) -> str:
    return "; ".join(f"{r['no']}. {r['title']}" for r in rows[:8])


def _slug(text: str, prefix: str = "") -> str:
    s = re.sub(r"\W+", "_", _strip_accents(str(text or "")).lower()).strip("_")[:40]
    return (prefix + s) if s else ""


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
        migrate(db)                                   # …before reading the array: it may create it
        if any(_norm(l.get("name")) == _norm(name) for l in db["taskLists"]):
            hit = next(l for l in lists(db) if _norm(l["name"]) == _norm(name))
            return {"ok": True, "list": hit["id"], "listNo": hit["no"], "existed": True}
        lid = _slug(name, "tl_") or f"tl_{int(time.time()) % 1000000}"
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
                                          f"ahora», tienes {_names(lists(db))}"}
        lst, why = pick_list(db, raw)
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
        db["tasks"] = [t for t in db.get("tasks", []) if str(t.get("listId") or "") != lst["id"]]
        if act == "clear_list":
            return {"ok": True, "list": lst["id"], "cleared": len(rows)}
        # The GENERAL list is not deletable — it is where a task with no home lands, and deleting it would
        # leave the next `add_task` writing into a list that does not exist. Emptying it is `clear_list`.
        if lst["id"] == GENERAL:
            return {"ok": True, "list": GENERAL, "cleared": len(rows), "kept_list": True}
        db["taskLists"] = [l for l in db.get("taskLists", []) if str(l.get("id")) != lst["id"]]
        return {"ok": True, "list": lst["id"], "deleted_list": True, "cleared": len(rows)}

    if act == "show_tasks":
        lst, why = pick_list(db, p.get("list") or p.get("name") or p.get("listId"))
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
        lst, why = pick_list(db, p.get("list") or p.get("listId"))
        if not lst:
            return {"ok": False, "error": why}
        migrate(db)
        tid = _slug(title, "t_") or f"t_{int(time.time()) % 1000000}"
        if any(t.get("id") == tid for t in db.get("tasks", [])):
            tid = f"{tid}_{int(time.time()) % 100000}"     # same slug twice is a second task, not a lost write
        t = {"id": tid, "title": title, "status": "todo", "listId": lst["id"], "createdAt": _today()}
        _details(t, p)
        db.setdefault("tasks", []).append(t)
        return {"ok": True, "task": tid, "list": lst["id"], "no": len(items(db, lst["id"]))}

    if act in ("update_task", "delete_task", "done", "drop", "snooze", "not_now"):
        lst, why = pick_list(db, p.get("list") or p.get("listId"))
        if not lst:
            return {"ok": False, "error": why}
        tid = str(p.get("taskId") or "").strip()
        t = _raw_task(db, tid) if tid else None
        if t is None:
            t, why = pick_task(db, lst, p.get("task") or p.get("item") or p.get("title") or tid)
            if t is None:
                return {"ok": False, "error": why}
        if act == "delete_task":
            db["tasks"] = [x for x in db.get("tasks", []) if x.get("id") != t["id"]]
            return {"ok": True, "task": t["id"], "deleted": str(t.get("title") or "")}
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
                dest, why = pick_list(db, moved)
                if not dest:
                    return {"ok": False, "error": why}
                t["listId"] = dest["id"]
            st = _norm(p.get("status"))
            if st:
                t["status"] = ("done" if ("hech" in st or "done" in st or "complet" in st)
                               else "todo" if ("pend" in st or "todo" in st or "sin" in st)
                               else t.get("status", "todo"))
            _details(t, p)
        return {"ok": True, "task": t["id"], "list": str(t.get("listId") or GENERAL)}

    return {"ok": False, "error": f"la agenda no sabe hacer «{act}» con una tarea"}


def _details(t: dict, p: dict) -> None:
    """The optional facts, each written ONLY when it arrived. A missing duration is what keeps a checklist
    item out of the day plan (see `plannable`), so defaulting one here would undo the whole rule."""
    raw_date = str(p.get("date") or p.get("day") or "").strip()
    if raw_date:
        t["date"] = _resolve_date(raw_date)
    raw_time = str(p.get("time") or p.get("startTime") or p.get("at") or "").strip()
    if raw_time:
        t["startTime"] = _resolve_time(raw_time)
        t["fixed"] = True
    for key, cast in (("estimateMinutes", int), ("priority", int)):
        if p.get(key) not in (None, ""):
            try:
                t[key] = cast(p[key])
            except Exception:  # noqa: BLE001 — a junk estimate costs the field, never the task
                pass
    if p.get("projectId"):
        t["projectId"] = str(p["projectId"])
    if p.get("deep"):
        t["deep"] = True


# ── what the brain reads ───────────────────────────────────────────────────────────────────────────────

def digest(db: dict, cap: int = 12) -> str:
    """The TASKS half of `index.prompt_digest`, built from the very same numbering the render shows — the
    V2-707 rule: two views of one card that disagree about what «the second one» is are worse than one."""
    ls = lists(db)
    live = [l for l in ls if l["total"]]
    if not live:
        return ""
    out = ["tareas del operador — dile el NÚMERO tal como lo ve («la 2 de la compra»):"]
    for l in live[:6]:
        out.append(f"  · lista {l['no']}. «{l['name']}» ({l['done']}/{l['total']}) id={l['id']}")
        for r in items(db, l["id"])[:cap]:
            mark = "✓" if r["status"] == "done" else "·"
            when = (" " + r["date"] if r["date"] else "") + (" " + r["time"] if r["time"] else "")
            out.append(f"      {mark} {r['no']}. {r['title']}{when}")
    return "\n".join(out)


def ref_rows(db: dict) -> list[dict]:
    """Rows for `index.ref_index`: a task the operator can name, with its number and its list in the hint so
    a refusal's menu reads the way the screen does."""
    out = []
    for l in lists(db):
        for r in items(db, l["id"]):
            if r["status"] == "done":
                continue
            out.append({"id": r["id"], "label": r["title"], "field": "taskId",
                        "hint": f"{l['name']} #{r['no']}" + (f" {r['date']}" if r["date"] else "")})
    return out
