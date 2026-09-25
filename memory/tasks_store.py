"""memory/tasks_store.py — the STORAGE for a user task (V2-728).

The `tasks`/`task_artifacts` tables and nothing else. What OPENS a task, what makes it visible and when it
closes are RULES, and they live in `nucleo/` (the dispatcher, the worker session, the scheduler) — exactly
the boundary `memory/errands_store.py` keeps for its own table.

Why the task is a durable row at all. Operator, 2026-09-20: *«si le digo resérvame hora en un restaurante,
ya no quiero ir a nada más… ya me olvido de esa tarea»*. Forgetting only works if somebody else remembers,
and before this nobody did for long: live work sat in a RAM dict that a restart emptied, finished work in a
50-capped JSON blob, and the RESULT inside a widget sheet that a hard cap of eight deleted on the ninth
search. See the v6→v7 note in `memory/schema.py` for the five stores this replaces.

TWO WRITE RATES, and keeping them apart is the point. A task row changes a handful of times in its life
(created, started, waiting, finished); the worker's phase/step/pct change every second and stay in
`dispatch._SESSIONS`, in RAM, where they belong. Nothing here is on the voice path.

Every function fails SOFT, for the same reason the errand ledger does: a store that raises would take down
the turn that was merely trying to record what it had just been asked to do.
"""
from __future__ import annotations

import json
import time

from . import db as _db_mod

#: States a task is still ALIVE in — what the «En curso» sub-tab and the rail counter read.
LIVE_STATES = ("pending", "running", "waiting")
#: …and the ones it is over in. `cancelled` is kept apart from `failed` deliberately: the operator stopping
#: something is not the same event as it breaking, and a list that conflates them cannot be read.
DONE_STATES = ("done", "failed", "cancelled")

_COLUMNS = ("id", "title", "goal", "kind", "mode", "state", "visible", "origin", "schedule", "surface",
            "sheet", "trace_id", "parent_id", "outcome", "created_at", "started_at", "due_at", "finished_at")


def _row(r) -> dict:
    """One DB row → a plain dict, with `schedule` parsed back into an object."""
    d = dict(r)
    raw = d.get("schedule")
    if raw:
        try:
            d["schedule"] = json.loads(raw)
        except Exception:  # noqa: BLE001 — a corrupt blob is not worth losing the row over
            d["schedule"] = {}
    else:
        d["schedule"] = {}
    d["visible"] = bool(d.get("visible", 1))
    return d


# ── write ────────────────────────────────────────────────────────────────────────────────────────────────
def task_put(row: dict) -> None:
    """Insert or replace one task. The caller composes the row; this writes it and reindexes its text.

    `INSERT … ON CONFLICT DO UPDATE` rather than a separate create/update pair because both the dispatcher
    (which creates) and the worker (which closes) call it, and a caller that has to know which one it is
    gets it wrong the first time a task is re-dispatched.
    """
    now = int(time.time())
    tid = str(row.get("id") or "").strip()
    if not tid:
        return
    sch = row.get("schedule") or {}
    try:
        _db_mod.get_db().execute(
            "INSERT INTO tasks (id, title, goal, kind, mode, state, visible, origin, schedule, surface, "
            "sheet, trace_id, parent_id, outcome, created_at, started_at, due_at, finished_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET title=excluded.title, goal=excluded.goal, kind=excluded.kind, "
            "mode=excluded.mode, state=excluded.state, visible=excluded.visible, origin=excluded.origin, "
            "schedule=excluded.schedule, surface=excluded.surface, sheet=excluded.sheet, "
            "parent_id=excluded.parent_id, outcome=excluded.outcome, started_at=excluded.started_at, "
            "due_at=excluded.due_at, finished_at=excluded.finished_at",
            (tid, str(row.get("title") or ""), str(row.get("goal") or ""),
             str(row.get("kind") or "generic"), str(row.get("mode") or "now"),
             str(row.get("state") or "pending"), 1 if row.get("visible", True) else 0,
             str(row.get("origin") or "voz"),
             json.dumps(sch, ensure_ascii=False) if sch else "",
             str(row.get("surface") or ""), str(row.get("sheet") or ""),
             str(row.get("trace_id") or ""), str(row.get("parent_id") or ""),
             str(row.get("outcome") or ""), int(row.get("created_at") or now),
             int(row.get("started_at") or 0) or None,
             int(row.get("due_at") or 0) or None,
             int(row.get("finished_at") or 0) or None))
    except Exception:  # noqa: BLE001
        return
    _reindex(tid, str(row.get("title") or ""), str(row.get("goal") or ""))


def task_patch(task_id: str, **fields) -> None:
    """Change a few columns of an existing task. Unknown column names are ignored, never interpolated."""
    tid = str(task_id or "").strip()
    sets, args = [], []
    for k, v in fields.items():
        if k not in _COLUMNS or k == "id":
            continue
        if k == "schedule":
            v = json.dumps(v or {}, ensure_ascii=False) if v else ""
        elif k == "visible":
            v = 1 if v else 0
        sets.append(f"{k}=?")
        args.append(v)
    if not tid or not sets:
        return
    try:
        _db_mod.get_db().execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id=?", (*args, tid))
    except Exception:  # noqa: BLE001
        return
    if "title" in fields or "goal" in fields:
        cur = task_get(tid) or {}
        _reindex(tid, str(cur.get("title") or ""), str(cur.get("goal") or ""))


def _reindex(task_id: str, title: str, goal: str) -> None:
    """Keep `fts_tasks` in step with one row. Delete-then-insert because FTS5 has no upsert.

    Missing FTS5 is survivable — the candidate search degrades to a LIKE scan in `task_search`, which is
    slower and blunter but never absent. A store that raised here would lose the task itself over its index.
    """
    try:
        db = _db_mod.get_db()
        db.execute("DELETE FROM fts_tasks WHERE task_id=?", (task_id,))
        db.execute("INSERT INTO fts_tasks (task_id, title, goal) VALUES (?,?,?)", (task_id, title, goal))
    except Exception:  # noqa: BLE001
        pass


def task_forget(task_id: str) -> None:
    """Drop a task and everything hanging off it. Used by the reset paths and by the tests, not by the product:
    a finished task is history, and history is not tidied away behind the operator's back."""
    tid = str(task_id or "").strip()
    if not tid:
        return
    try:
        db = _db_mod.get_db()
        db.execute("DELETE FROM task_artifacts WHERE task_id=?", (tid,))
        db.execute("DELETE FROM fts_tasks WHERE task_id=?", (tid,))
        db.execute("DELETE FROM tasks WHERE id=?", (tid,))
    except Exception:  # noqa: BLE001
        pass


def tasks_clear(states: tuple = DONE_STATES, modes: tuple = ("now",)) -> int:
    """Drop whole task rows (and everything hanging off them). Returns how many went.

    This is the RESET's door and nothing else's. `modes=("now",)` is not a detail: a `scheduled` or
    `recurring` row is a standing commitment of the operator's — «avísame cada lunes» — and a reset of the
    work in progress has never meant «forget what I asked you to remember». Deleting those would also be
    pointless, since they are mirrors of the scheduler's own rows and `scheduler.reconcile_board()` would
    put them straight back, which is the worst of both: destructive AND ineffective.
    """
    if not states:
        return 0
    where = ["state IN (%s)" % ",".join("?" for _ in states)]
    args: list = list(states)
    if modes:
        where.append("mode IN (%s)" % ",".join("?" for _ in modes))
        args.extend(modes)
    cond = " AND ".join(where)
    try:
        db = _db_mod.get_db()
        rows = db.query(f"SELECT id FROM tasks WHERE {cond}", tuple(args))
        ids = [r["id"] for r in rows]
        for tid in ids:
            task_forget(tid)
        return len(ids)
    except Exception:  # noqa: BLE001
        return 0


def tasks_prune(max_age_days: float = 30.0, now: float | None = None) -> int:
    """Sleep-time hygiene: forget FINISHED work older than `max_age_days`. Returns how many went.

    The ledger this replaces had to prune at seven days because it was a 50-entry JSON blob re-serialised on
    every write. A table has neither problem, so the window is a month and the reason for having one at all
    is different: `task_artifacts` holds whole reports, and a year of them is real disk. What is pruned is
    the ROW and its artifacts; the memory pill written when the task closed is not touched here — that one
    ages by the memory's own decay, which is the mechanism for deciding what is still worth knowing.

    Nothing LIVE is ever pruned, whatever its age. A task still running after a month is a task that needs
    looking at, not one that needs deleting.
    """
    cutoff = int((time.time() if now is None else now) - max(0.0, float(max_age_days)) * 86400.0)
    try:
        db = _db_mod.get_db()
        rows = db.query(
            "SELECT id FROM tasks WHERE state IN (%s) AND COALESCE(finished_at, created_at) < ?"
            % ",".join("?" for _ in DONE_STATES), (*DONE_STATES, cutoff))
        ids = [r["id"] for r in rows]
        for tid in ids:
            task_forget(tid)
        return len(ids)
    except Exception:  # noqa: BLE001
        return 0


# ── read ─────────────────────────────────────────────────────────────────────────────────────────────────
def task_get(task_id: str) -> dict | None:
    try:
        rows = _db_mod.get_db().query("SELECT * FROM tasks WHERE id=?", (str(task_id),))
        return _row(rows[0]) if rows else None
    except Exception:  # noqa: BLE001
        return None


def tasks_where(states: tuple = LIVE_STATES, *, modes: tuple = (), visible_only: bool = True,
                limit: int = 100, newest_first: bool = False) -> list[dict]:
    """Tasks matching a state (and optionally a mode). The defaults are what the «En curso» sub-tab asks for.

    `visible_only` is the admission gate the operator chose: the list shows HIS commissions, and the internal
    ones (memory maintenance, dev, relays) only when the `⚙ todo` switch asks for them.
    """
    if not states:
        return []
    where = ["state IN (%s)" % ",".join("?" for _ in states)]
    args: list = list(states)
    if modes:
        where.append("mode IN (%s)" % ",".join("?" for _ in modes))
        args.extend(modes)
    if visible_only:
        where.append("visible=1")
    order = "COALESCE(finished_at, created_at) DESC" if newest_first else "created_at ASC"
    try:
        rows = _db_mod.get_db().query(
            f"SELECT * FROM tasks WHERE {' AND '.join(where)} ORDER BY {order} LIMIT ?",
            (*args, int(limit)))
        return [_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def tasks_children(parent_id: str) -> list[dict]:
    """The rows whose `parent_id` is this one, in id order — the steps of a list (V2-771)."""
    try:
        rows = _db_mod.get_db().query("SELECT * FROM tasks WHERE parent_id=? ORDER BY id ASC", (str(parent_id),))
        return [_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def tasks_of_kind(kind: str, states: tuple = LIVE_STATES) -> list[dict]:
    """Every row of one kind in these states, visible or not — what a boot-time resume needs (V2-771)."""
    if not states:
        return []
    try:
        rows = _db_mod.get_db().query(
            "SELECT * FROM tasks WHERE kind=? AND state IN (%s) ORDER BY created_at ASC"
            % ",".join("?" for _ in states), (str(kind), *states))
        return [_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def tasks_due(now: float | None = None, limit: int = 20) -> list[dict]:
    """Scheduled/recurring tasks whose moment has arrived. Read once a second by the loop, so it is indexed."""
    ts = int(time.time() if now is None else now)
    try:
        rows = _db_mod.get_db().query(
            "SELECT * FROM tasks WHERE due_at IS NOT NULL AND due_at <= ? AND state='pending' "
            "AND mode IN ('scheduled','recurring') ORDER BY due_at ASC LIMIT ?", (ts, int(limit)))
        return [_row(r) for r in rows]
    except Exception:  # noqa: BLE001
        return []


def task_search(query: str, limit: int = 5) -> list[dict]:
    """Candidate tasks for a fuzzy reference («the flat-hunting task I told you about»), NEWEST FIRST.

    LEXICAL ONLY, and that is the requirement, not a shortcut: the operator's rule (INI-027 §7) is that the
    candidate search costs no model — an index narrows to ≤5 and a model only CHOOSES among those. The
    chooser is `nucleo/jev.py::select_many`; it is not called from here, because storage does not decide.

    Falls back to LIKE when FTS5 is unavailable or the query has no usable token: blunter, still an answer.
    """
    q = (query or "").strip()
    if not q:
        return []
    ids: list[str] = []
    try:
        # One MATCH over the words that survive tokenising. `OR` rather than the default AND: a reference is
        # a paraphrase, not a quotation, and requiring every word finds nothing far more often than it
        # should. Ranking, not filtering, is what narrows it — that is what bm25 is for.
        words = [w for w in "".join(c if c.isalnum() or c.isspace() else " " for c in q).split() if len(w) > 2]
        if words:
            expr = " OR ".join(words)
            rows = _db_mod.get_db().query(
                "SELECT task_id FROM fts_tasks WHERE fts_tasks MATCH ? ORDER BY bm25(fts_tasks) LIMIT ?",
                (expr, int(limit) * 3))
            ids = [r["task_id"] for r in rows]
    except Exception:  # noqa: BLE001
        ids = []
    if not ids:
        try:
            rows = _db_mod.get_db().query(
                "SELECT id FROM tasks WHERE visible=1 AND (title LIKE ? OR goal LIKE ?) "
                "ORDER BY created_at DESC LIMIT ?", (f"%{q}%", f"%{q}%", int(limit)))
            ids = [r["id"] for r in rows]
        except Exception:  # noqa: BLE001
            return []
    out = []
    for tid in ids:
        row = task_get(tid)
        # Only the operator's own commissions are offered back to him: an internal relay is not something he
        # can have «told us about before».
        if row and row.get("visible"):
            out.append(row)
    out.sort(key=lambda r: -(r.get("created_at") or 0))
    return out[:int(limit)]


# ── artifacts ────────────────────────────────────────────────────────────────────────────────────────────
def artifact_put(task_id: str, slot: str, payload) -> None:
    """Store one part of a task's result. Replaces that slot; the others are untouched."""
    tid, sl = str(task_id or "").strip(), str(slot or "").strip()
    if not tid or not sl:
        return
    try:
        _db_mod.get_db().execute(
            "INSERT INTO task_artifacts (task_id, slot, payload, created_at) VALUES (?,?,?,?) "
            "ON CONFLICT(task_id, slot) DO UPDATE SET payload=excluded.payload, "
            "created_at=excluded.created_at",
            (tid, sl, json.dumps(payload, ensure_ascii=False), int(time.time())))
    except Exception:  # noqa: BLE001
        pass


def artifact_get(task_id: str, slot: str):
    try:
        rows = _db_mod.get_db().query(
            "SELECT payload FROM task_artifacts WHERE task_id=? AND slot=?", (str(task_id), str(slot)))
        if not rows:
            return None
        raw = rows[0]["payload"]
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return None


def artifacts_of(task_id: str) -> dict:
    """Every stored part of one task's result, keyed by slot. What rebuilds a pruned sheet."""
    out: dict = {}
    try:
        rows = _db_mod.get_db().query(
            "SELECT slot, payload FROM task_artifacts WHERE task_id=?", (str(task_id),))
        for r in rows:
            slot, raw = r["slot"], r["payload"]
            try:
                out[slot] = json.loads(raw)
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        return {}
    return out
