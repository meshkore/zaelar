"""nucleo/circuit/progress.py — a task row's state AS IT MOVES, on the timeline (`task_progress`).

`circuit.settle` says ONCE how a row ended (`task_state`). Everything before that — its birth, the plan its worker
reported, the question it waits on, a worker that died and is resumed, the name that arrived — was written into the row
and nowhere else, so a replay of a session could not say where a task stood at any moment of it.

Every door that moves a row calls `changed` with the row as it was BEFORE its write; this reads the row after it and
emits ONE `task_progress` event with what changed (a delta), named by its writer. A birth or an open carries the whole
row instead (a snapshot), and with it what the task must show when it ends — its harness, the end state the circuit
judges it by — and the playbook it follows. A row that changed nothing emits nothing.

Mechanism only: no vocabulary is read, every text is bounded, and nothing here raises or decides anything.
"""
from __future__ import annotations

from loguru import logger

KIND = "task_progress"
#: The longest text a field carries on the timeline, and the most items a list does (a plan, its resolved steps).
TEXT_CAP, LIST_CAP = 400, 12


def _fields(row: dict) -> list[str]:
    """The row's columns a replay reads: every column the store returns, except its id and its CLOCKS (`*_at`). A clock
    is when something happened, which the event's own time already says — and the two the pulse rewrites on every beat
    (`heartbeat_at`, `reported_at`) would make a delta of one event per beat for every live task. Read off the row
    itself, so a column the store gains is carried without a second list of them here."""
    return [k for k in row if k != "id" and not k.endswith("_at")]


def _bound(v, depth: int = 0):
    """A value as the timeline carries it: texts cut at `TEXT_CAP`, lists at `LIST_CAP`, nesting two levels deep."""
    if isinstance(v, str):
        return v[:TEXT_CAP]
    if isinstance(v, (list, tuple)):
        return [_bound(x, depth + 1) for x in list(v)[:LIST_CAP]]
    if isinstance(v, dict):
        if depth >= 2:
            return str(v)[:TEXT_CAP]
        return {str(k): _bound(x, depth + 1) for k, x in v.items()}
    if v is None or isinstance(v, (int, float, bool)):
        return v
    return str(v)[:TEXT_CAP]


def _field(k: str, v):
    """One column, bounded — and the progress with the steps of its plan already behind it (`resolved`)."""
    if k != "progress" or not isinstance(v, dict):
        return _bound(v)
    out = _bound(v)
    plan, done = v.get("plan"), v.get("done")
    if isinstance(plan, list) and isinstance(done, int) and done > 0:
        out["resolved"] = _bound(plan[:done])
    return out


def harness_of(e: dict | None) -> dict:
    """What the task must show when it ends, read from its spec entry (`spec.open`/`spec.of_task`): the end state in one
    line, the card it names, how far its checking went. {} when the task has none."""
    if not isinstance(e, dict) or not e.get("done_when"):
        return {}
    try:
        from nucleo.circuit import verify as _verify
        said = _verify.describe(e.get("done_when"))
    except Exception as ex:  # noqa: BLE001 — an unreadable end state is still named by its target
        said = str(logger.debug(f"progress: end state not described — {ex!r}") or "")
    out = {"end_state": said, "target": e.get("target"), "status": e.get("status"), "source": e.get("source"),
           "checks": e.get("checks"), "tries": e.get("tries")}
    if e.get("unverifiable"):
        out["unverifiable"] = True
    return {k: _bound(v) for k, v in out.items() if v not in (None, "")}


def _harness(uid: str) -> dict:
    """The row's harness, read through the spec module only when it is already loaded: an emit never IMPORTS it — these
    run on pool threads, and an import there races whatever else is loading it. Every door that opens an end state
    (`spec.open`, a relaunch's `_born`, a restart's judgement) has loaded it first, so nothing owed is missed."""
    import sys
    _spec = sys.modules.get("nucleo.circuit.spec")
    if _spec is None or not hasattr(_spec, "of_task"):
        return {}
    try:
        return harness_of(_spec.of_task(uid))
    except Exception as ex:  # noqa: BLE001
        return {"error": str(logger.debug(f"progress: harness of {uid} unreadable — {ex!r}") or type(ex).__name__)}


def _line(row: dict) -> str:
    """The one readable line of the row's state, for the ◷ viewer's message column."""
    p = row.get("progress") if isinstance(row.get("progress"), dict) else {}
    bits = [str(row.get("state") or "")]
    if row.get("phase"):
        bits.append(str(row["phase"]))
    if p.get("total"):
        bits.append(f"{p.get('done') or 0}/{p['total']}")
    if row.get("waiting_for"):
        bits.append(f"waits {row['waiting_for']}")
    if p.get("note"):
        bits.append(str(p["note"]))
    return " · ".join(b for b in bits if b)[:200]


def _send(uid: str, writer: str, row: dict, delta: dict, *, snapshot: bool = False, harness: dict | None = None,
          gone: bool = False) -> None:
    from voice import observer
    extra = {"task_id": uid, "writer": writer, "state": str(row.get("state") or ""), "delta": delta}
    if row.get("trace_id"):
        extra["trace"] = str(row["trace_id"])
    if snapshot:
        extra["snapshot"] = True
    if harness:
        extra["harness"] = harness
    if gone:
        extra["gone"] = True
    observer.emit(KIND, f"📋 task {extra['state'] or 'gone'} ({writer})", text=_line(row), role="system", extra=extra)


def changed(uid: str, writer: str, before: dict | None, *, snapshot: bool = False, harness: bool = False) -> None:
    """Emit what `writer` changed on row `uid`, measured against `before` (the row as it was before the write). With
    `snapshot` (a birth, an open) the whole row goes; with `harness` its harness rides along (an open: what it will be
    judged by; an ending: how far its checking went). A row born in the turn has no end state yet — it is opened with it,
    and `harness_set` says it then — so a birth asks for none. Nothing changed → nothing emitted. Never raises."""
    uid = str(uid or "").strip()
    if not uid:
        return
    try:
        from nucleo.circuit import ledger
        row = ledger.store().task_get(uid)
        if row is None:
            return
        prev = {} if snapshot or before is None else dict(before)
        delta = {k: _field(k, row.get(k)) for k in _fields(row)
                 if (row.get(k) not in (None, "", {}, []) if not prev else row.get(k) != prev.get(k))}
        if not delta and not snapshot:
            return
        _send(uid, writer, row, delta, snapshot=snapshot or before is None,
              harness=_harness(uid) if harness else None)
    except Exception as e:  # noqa: BLE001 — evidence that cannot be emitted never changes how a task goes
        logger.debug(f"progress: {KIND} of {uid} not emitted — {type(e).__name__}: {e}")


def harness_set(uid: str, e: dict) -> None:
    """The task's end state was opened (at its birth, inferred later, or stated by its worker at checkpoint 1): the row
    did not change, what it will be judged by did. Never raises."""
    uid = str(uid or "").strip()
    h = harness_of(e)
    if not uid or not h:
        return
    try:
        from nucleo.circuit import ledger
        row = ledger.store().task_get(uid)
        if row is not None:
            _send(uid, "spec", row, {}, harness=h)
    except Exception as ex:  # noqa: BLE001
        logger.debug(f"progress: harness of {uid} not emitted — {type(ex).__name__}: {ex}")


def gone(uid: str, writer: str, before: dict | None) -> None:
    """The row was FORGOTTEN (a birth nobody adopted, a commission withdrawn at its gate): said once, so a replay does not
    keep a task alive that no longer exists. Never raises."""
    uid = str(uid or "").strip()
    if not uid or before is None:
        return
    try:
        _send(uid, writer, dict(before), {}, gone=True)
    except Exception as ex:  # noqa: BLE001
        logger.debug(f"progress: {uid} gone not emitted — {type(ex).__name__}: {ex}")
