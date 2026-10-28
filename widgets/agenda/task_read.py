"""widgets/agenda/task_read.py — READING the operator's task lists: the lists, their items, the view he is on, picking a list or a task by what he says, and the digest (split from `tasklists.py`)."""
from __future__ import annotations

import re
import time
from .when import _strip_accents, _resolve_date, _resolve_time, _today


#: The built-in list every task without a home belongs to. Its NAME is stored so the operator can rename it
#: like any other; the widget translates the untouched default, which is the same word in both languages.
GENERAL = "general"


GENERAL_NAME = "General"


#: How long a pushed tasks view stays worth obeying — the same TTL and the same reason as `data._VIEW_TTL_S`:
#: «ábreme la lista de la compra» then `show_widget` has to arrive already pointing at it, and a push kept
#: for ever would yank the list he is reading a week later.
_VIEW_TTL_S = 600


_LIVE = (None, "todo", "in_progress")


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


#: The payload keys through which the manifest names an EXISTING task / an existing list. A row is published
#: once per key, because `refs.id_field_for_action` answers with the key the ACTION declares and there is more
#: than one: `done`/`drop`/`snooze`/`not_now` take `taskId` (the V2-026 suffix convention), while
#: `update_task`/`delete_task` declare `ref: "task"` — the key the operator's own sentence fills («la 2»).
#:
#: V2-747, measured in session 16a39050: he said «modifica la tarea número tres con crear la nueva cuenta…»,
#: the model picked `agenda:update_task` with the reference «la tarea 3 de la lista Obra» — both right — and
#: the resolution returned `no_match` with an EMPTY candidate list, so he got «No tengo claro a cuál te
#: refieres» over three tasks that were sitting in the card. The index published `taskId` only, so for the two
#: actions that CHANGE a task there was not one row to match against: not a bad match, no rows at all.
_TASK_FIELDS = ("taskId", "task")


_LIST_FIELDS = ("list",)


def ref_rows(db: dict) -> list[dict]:
    """Rows for `index.ref_index`: everything the operator can name by voice, with the number the SCREEN shows
    beside it (`no`) and the list it is printed under (`group`).

    `no`/`group` are what make «la tarea 3 de la lista Obra» resolvable — see `refs._numbered_ref`. They are
    NOT the fuzzy matcher's business: the number he says is the number he is reading, so it is looked up, and
    a bare number that means two different rows in two lists is a QUESTION, never a guess."""
    out = []
    for l in lists(db):
        for r in items(db, l["id"]):
            if r["status"] == "done":
                continue
            hint = f"{l['name']} #{r['no']}" + (f" {r['date']}" if r["date"] else "")
            for f in _TASK_FIELDS:
                out.append({"id": r["id"], "label": r["title"], "field": f, "hint": hint,
                            "no": r["no"], "group": l["name"]})
    for l in lists(db):
        hint = f"#{l['no']} · {l['done']}/{l['total']}"
        for f in _LIST_FIELDS:
            out.append({"id": l["id"], "label": l["name"], "field": f, "hint": hint, "no": l["no"]})
    return out
