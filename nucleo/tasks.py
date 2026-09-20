"""nucleo/tasks.py — the SessionRecord ↔ durable task row seam (V2-728).

One place that knows how a live Brain Worker session becomes a row in `tasks`, because the two vocabularies
do not match and a translation written twice comes to differ. `memory/tasks_store.py` stores; this decides.

THREE THINGS LIVE HERE AND NOTHING ELSE:

  1. **The durable id.** `escalate._seq` returns to 0 in every process, so a `task_id` does not identify a
     commission beyond the engine's lifetime — the defect `nucleo/runtime_ids.py` was written for, and the one
     that made a fresh errand land on the previous session's sheet and delete it (V2-259). Composed with
     `boot_id()`, exactly as `sheets.sheet_id_for` composes the sheet id, and for the same reason.
  2. **The state vocabulary.** A worker says `queued|running|done|error|cancelled|relevada`; a task says
     `pending|running|waiting|done|failed|cancelled`. They are not the same list and the differences carry
     meaning: `relevada` is NOT an ending (a relay continues the same commission), and `waiting` is not a
     state the worker has at all — it is `waiting_on` being set.
  3. **The admission gate.** Which escalations are the OPERATOR's commissions, and which are the engine
     talking to itself. Deterministic, by origin and kind — never a model call: a list whose contents depend
     on a classifier is a list the operator cannot predict, and this one has to be boring.
"""
from __future__ import annotations

import time

from memory import tasks_store as _ts
from nucleo.runtime_ids import boot_id as _boot_id

#: Worker status → task state. `relevada` maps to `running` deliberately: a relay picks the same commission up
#: with a fresh worker, and painting it «done» for the seconds in between is how a task the operator is still
#: waiting for shows up in the finished list.
_STATE = {"queued": "pending", "running": "running", "done": "done",
          "error": "failed", "cancelled": "cancelled", "relevada": "running"}

#: Escalations the engine makes to itself. These get a row (the audit trail is worth having) but never the
#: counter, the list or a place in `task_recall` — the operator cannot have «told us about» a memory
#: consolidation. Keyed on the escalation's `src`/`kind`, both of which the caller already sets.
_INTERNAL_KINDS = frozenset({"memory", "dev"})
_INTERNAL_SRC = frozenset({"goal_unmet", "context_handoff", "provider_handoff", "auto_resume", "rehydrate"})


def task_uid(task_id) -> str:
    """The DURABLE id of a commission. Same composition as `sheets.sheet_id_for`, on purpose: one errand is
    one sheet is one task, so the two ids are trivially joinable when reading a trail by hand."""
    return f"{_boot_id()}-{str(task_id or '').strip()}"


def state_of(rec) -> str:
    """A live record's state in the task vocabulary. `waiting_on` wins: a worker parked on a question is
    `running` as far as the runtime is concerned, and that is precisely not what the operator needs to see."""
    status = str(getattr(rec, "status", "") or "queued")
    if str(getattr(rec, "waiting_on", "") or "") and status in ("queued", "running"):
        return "waiting"
    return _STATE.get(status, "running")


def is_visible(kind: str = "", src: str = "", origin: str = "voz") -> bool:
    """Is this the operator's own commission? Deterministic: origin and kind, no model, no heuristics.

    The rule the operator set (2026-09-20): the list is HIS commissions, and the internal ones show only
    behind the `⚙ todo` switch — which he needs during a manual test, when «why is the agent busy» is exactly
    the question.
    """
    if str(kind or "").strip().lower() in _INTERNAL_KINDS:
        return False
    if str(src or "").strip().lower() in _INTERNAL_SRC:
        return False
    return str(origin or "voz").strip().lower() not in ("worker",)


def opened(rec, ctx: dict | None = None) -> str:
    """Record a commission as it is dispatched. Returns the durable id (also stamped onto `rec.uid`).

    A RELAY does not open a second task. It arrives carrying the `task_uid` of the commission it continues
    (the same way it already carries the sheet, `nucleo/workers/relay.py`), and this updates that row instead
    — otherwise one errand that changed provider twice reads as three separate things the operator asked for.
    """
    ctx = dict(ctx or {})
    inherited = str(ctx.get("task_uid") or "").strip()
    uid = inherited or task_uid(getattr(rec, "task_id", ""))
    try:
        rec.uid = uid
    except Exception:  # noqa: BLE001 — a record that will not take an attribute is still worth recording
        pass
    now = int(time.time())
    if inherited and _ts.task_get(inherited):
        # Continuation: the name, the goal and the origin are the ORIGINAL commission's and must not be
        # overwritten by the relay's rewritten brief (which carries «[ARNÉS] esto quedó sin cumplir…»).
        _ts.task_patch(inherited, state="running", kind=str(getattr(rec, "kind", "") or "generic"),
                       sheet=str(getattr(rec, "sheet", "") or ""), finished_at=None, outcome="")
        return uid
    _ts.task_put({
        "id": uid,
        "title": str(getattr(rec, "title", "") or ""),
        "goal": str(getattr(rec, "goal", "") or ""),
        "kind": str(getattr(rec, "kind", "") or "generic"),
        "mode": "now",
        "state": state_of(rec),
        "visible": is_visible(kind=str(getattr(rec, "kind", "") or ""), src=str(ctx.get("src") or ""),
                              origin=str(ctx.get("origin") or "voz")),
        "origin": str(ctx.get("origin") or "voz"),
        "surface": str(getattr(rec, "surface", "") or ""),
        "sheet": str(getattr(rec, "sheet", "") or ""),
        "trace_id": str(getattr(rec, "trace_id", "") or ""),
        "parent_id": str(ctx.get("parent_task_uid") or ""),
        "created_at": int(getattr(rec, "started", now) or now),
        "started_at": now,
    })
    return uid


def retitled(rec) -> None:
    """The NAME arrived (V2-530 composes it asynchronously, seconds after the sheet opened). Without this the
    row keeps the provisional clip forever — and the title is half of what `task_search` matches on."""
    uid = str(getattr(rec, "uid", "") or "")
    if not uid:
        return
    _ts.task_patch(uid, title=str(getattr(rec, "title", "") or ""))


def closed(rec, *, outcome: str = "") -> None:
    """The commission is over: its state, its outcome, and its RESULT are recorded.

    A relay is NOT over — `relevada` maps to `running`, so the row stays live while the baton is in the air,
    which is what the operator is actually waiting on, and nothing is snapshotted yet.
    """
    uid = str(getattr(rec, "uid", "") or "")
    if not uid:
        return
    # THE FENCE. A reset kills the live workers and then wipes the board; a kill is a signal, so the dying
    # worker's finish path lands MILLISECONDS LATER and used to write its own tombstone onto the fresh slate
    # — the operator reset, and the one thing «Hechas» showed was the search his reset had just cancelled
    # (seen live 2026-08-31, V2-084). The ledger fenced that with a stored «cleared at» timestamp and a
    # comparison in every writer. Here the question is asked directly instead: does this task still exist?
    # A row the reset deleted is not one to be closed, and reordering the reset would only narrow the
    # window, never shut it, because the worker's death is not ours to sequence.
    if _ts.task_get(uid) is None:
        return
    state = state_of(rec)
    if state in ("running", "pending", "waiting"):
        _ts.task_patch(uid, state=state)
        return
    said = (outcome or str(getattr(rec, "result_summary", "") or ""))[:400]
    _ts.task_patch(uid, state=state, finished_at=int(time.time()), outcome=said)
    kept_result(rec)
    remembered(rec, state=state, outcome=said)


def kept_result(rec) -> None:
    """Copy this errand's sheet into `task_artifacts`, so the RESULT outlives the sheet.

    Operator, 2026-09-20: *«si hemos pedido unos resultados para encontrar piso… todo eso tiene que quedar
    vinculado»*. It did not. `widgets/results/sheet_names.py` keeps at most EIGHT instantiated sheets and
    prunes the rest by file mtime, so the ninth search silently deleted the report of the first — a report
    the sheet's own header comment says exists precisely so «the operator does not lose a report he already
    paid for». One cap contradicted the other.

    The sheet stays where it is and stays the thing on screen; this is the copy the task owns. `sheet_of(rec)`
    and `task_uid` compose the same string by construction (see `task_uid`), so the two are the same object
    seen from either side and no id has to be threaded through the widget layer.

    THE DISCARDED ONES ARE HERE TOO, and getting them here was a change to what the WORKER REPORTS, not to
    where anything is stored: until V2-728 a rejection survived only as a count (`hbnote considered N --kept
    M`, V2-059), so «los 50 que descartó» existed nowhere to be copied. The sheet now has a `rejected` list
    of argued rows (`widgets/results/data.py`, action `rejected`) and they travel with the rest.
    """
    uid = str(getattr(rec, "uid", "") or "")
    sheet = str(getattr(rec, "sheet", "") or "")
    if not uid or not sheet:
        return
    try:
        from widgets.results import data as _sheet
        payload = _sheet.view_data(sheet)
    except Exception:  # noqa: BLE001 — a snapshot that failed must not change how the errand ended
        return
    if not isinstance(payload, dict) or not payload:
        return
    # The report itself, whole. Split by SLOT so «enséñame los descartados» need not load the kept ones, and
    # so the criteria —what `jev.select_many` scores a later question against— can be read on their own.
    _ts.artifact_put(uid, "result", {k: v for k, v in payload.items()
                                     if k not in ("criteria", "sources", "process", "rejected")})
    for slot in ("criteria", "sources", "process"):
        if payload.get(slot):
            _ts.artifact_put(uid, slot, payload[slot])
    # …and what was REJECTED: the rows with their reasons, plus the breadth the worker reported. Both, and
    # they are not the same number: `considered` counts everything it looked at (including what it never
    # bothered to write down), `rows` is what it argued about. Stored even when the rows are empty, because
    # «mirados 50, guardados 5, y no dijo por qué de ninguno» is itself a true and readable answer.
    rows = payload.get("rejected") if isinstance(payload.get("rejected"), list) else []
    considered, kept = int(getattr(rec, "considered", -1) or -1), int(getattr(rec, "kept", -1) or -1)
    if considered >= 0 or kept >= 0 or rows:
        _ts.artifact_put(uid, "considered",
                         {"considered": considered, "kept": kept, "rows": rows})


def remembered(rec, *, state: str = "done", outcome: str = "") -> None:
    """Write the closed commission into CENTRAL MEMORY as one pill: `[task:<uid>] <title> — <outcome>`.

    WHY A SECOND RECORD AT ALL, when `tasks` already holds the row. The two answer different questions and
    only one of them is asked mid-sentence. `task_search` is a lexical index: it answers «which task do these
    WORDS name», which is what `task_recall` needs once the operator has already said he means a task. Recall
    answers «what do I know that bears on what he just said», and it runs on every turn without being asked.
    Before this the tasks were invisible to it, so «¿encontraste algo de pisos?» —a question that never uses
    the word *tarea*— retrieved the conversation about flats and not the errand that went and found five.

    The pill is a NORMAL pill and that is the point: it goes through `memory.write` like everything else, so
    the writer embeds it, indexes it and —because `concepts` is left empty— derives its graph edges with the
    same deterministic `derive_concepts` backstop every other durable pill gets. «Que todo eso quede
    vinculado» is that edge set, not a bespoke join table: a task about flats hangs off the same concept hub
    as everything else the operator knows about flats, and `expand()` reaches it from either side.

    SUPERSEDE, not append. A commission can close more than once (a relay hands the baton back, a re-dispatch
    reopens it). `task_trace_ids` hands over the earlier chapters so only the newest stays valid — the
    lesson of V2-577, where a widget's birth announcement outlived its own tombstone and the next worker
    believed the wrong one.

    `meta.task_id` is what makes the pill actionable rather than merely readable: whoever recall hands it to
    can reopen the report itself (`widgets/results/rehydrate.sheet_from_task`). It is also the only durable
    join between the two records, and it is a field rather than an `edges` row for the honest reason that an
    edge joins two MEMORY ids and a task is not one.
    """
    uid = str(getattr(rec, "uid", "") or "")
    if not uid:
        return
    title = str(getattr(rec, "title", "") or "").strip()
    goal = str(getattr(rec, "goal", "") or "").strip()
    name = title or goal
    if not name:
        return
    verb = {"done": "terminó", "failed": "falló", "cancelled": "se canceló"}.get(state, "terminó")
    when = time.strftime("%Y-%m-%d", time.localtime())
    line = f"[task:{uid}] El encargo «{name[:160]}» {verb} el {when}."
    if outcome and outcome.strip() != name:
        line += f" Resultado: {outcome.strip()[:240]}"
    if title and goal and goal != title:
        # The operator's OWN words are what a later reference paraphrases; the composed name is a summary of
        # them and does not always share a single content word with what he actually said.
        line += f" Lo pidió así: «{goal[:200]}»."
    try:
        from memory import api as _memory
        _memory.write(line, kind="event", level="mid", importance=0.55,
                      supersedes=_memory.task_trace_ids(uid) or None,
                      meta={"source": "task", "task_id": uid,
                            "task_kind": str(getattr(rec, "kind", "") or ""), "task_state": state})
    except Exception:  # noqa: BLE001 — a commission that finished is not undone by a memory that did not
        return


# ── errands (V2-683) ─────────────────────────────────────────────────────────────────────────────────────
#: An errand's own state machine → the task vocabulary. Every LIVE state is `running` from the operator's
#: side: whether we are contacting, negotiating or gathering is detail for the row's second line, not a
#: different answer to «is this still going?».
_ERRAND_STATE = {"gathering": "running", "contacting": "running", "negotiating": "running",
                 "agreed": "running", "closed": "done", "abandoned": "cancelled", "blocked": "failed"}


def errand_uid(errand_id) -> str:
    """The task id of an errand. Namespaced rather than bare so a trail read by hand says what it came from;
    the errand's own id is already durable (`errands.new_id()`), so nothing is composed with `boot_id`."""
    return f"errand:{str(errand_id or '').strip()}"


def errand_mirrored(row: dict) -> None:
    """Keep the `tasks` row of an errand in step with the `errands` row.

    An errand is a commission like any other from where the operator sits — it just happens to be carried by
    a conversation with somebody rather than by a worker. Before this it had to be SYNTHESISED into the board
    at the HTTP route (`errands.board_rows`), which is why the board had two row shapes stitched by hand.

    The errand keeps its own table: its state machine, its deadlines and its thread bindings are real columns
    that a generic task row would flatten, and —the reason it was a table in the first place— its silence is
    not a stalled worker. This mirrors what the BOARD needs and leaves the rest where it is.
    """
    if not isinstance(row, dict) or not row.get("id"):
        return
    state = _ERRAND_STATE.get(str(row.get("state") or ""), "running")
    closed = int(row.get("closed_at") or 0)
    _ts.task_put({
        "id": errand_uid(row["id"]),
        "title": str(row.get("title") or row.get("objective") or ""),
        "goal": str(row.get("objective") or ""),
        "kind": "encargo",
        "mode": "now",
        "state": state,
        "visible": True,
        "origin": "voz",
        "surface": "voz",
        "trace_id": str(row.get("trace_id") or ""),
        "outcome": str(row.get("outcome") or "")[:400],
        "created_at": int(row.get("created_at") or 0),
        "started_at": int(row.get("created_at") or 0),
        "finished_at": closed if state in ("done", "failed", "cancelled") else 0,
    })


# ── the operator's board ─────────────────────────────────────────────────────────────────────────────────
#: Which sub-tab of «Tareas» asks for what. A closed vocabulary, for the reason `surfaces.py` keeps one: an
#: open string drifts into a taxonomy nobody maintains and the frontend starts guessing.
SCOPES = ("live", "done", "recurring", "scheduled")


def board(scope: str = "live", *, show_all: bool = False) -> list[dict]:
    """The rows behind one sub-tab, with the live detail merged on top.

    This is the whole read path of the task board, and it lives in `nucleo/` rather than in the route for
    two reasons. The layering one: the HTTP surface should ask the brain for the board, not reach into the
    memory package — which is also what keeps `memory.tasks_store` down to a single production importer and
    the boundary ratchet honest. And the durable one: the row is what is TRUE (name, goal, state, hours),
    while the phase, the plan, the percentage and the question a worker is parked on change every second and
    live in RAM. Merging them anywhere else means two places that both half-know what a task is.
    """
    scope = (scope or "live").strip().lower()
    if scope not in SCOPES:
        scope = "live"
    if scope == "done":
        rows = _ts.tasks_where(states=_ts.DONE_STATES, modes=("now",), visible_only=not show_all,
                               limit=60, newest_first=True)
    elif scope in ("recurring", "scheduled"):
        rows = _ts.tasks_where(states=("pending", "running", "waiting"), modes=(scope,),
                               visible_only=not show_all, limit=100)
    else:
        rows = _ts.tasks_where(states=_ts.LIVE_STATES, modes=("now",), visible_only=not show_all, limit=100)
    if not rows:
        return []
    live: dict = {}
    try:
        from nucleo import dispatch
        live = {str(x.get("uid") or ""): x for x in dispatch.active_sessions() if x.get("uid")}
    except Exception:  # noqa: BLE001 — a board with no live detail is still a board
        pass
    phases: dict = {}
    try:
        from nucleo import errands
        phases = errands.live_phases()      # «esperando respuesta · quedan 2 h» — derived from a clock
    except Exception:  # noqa: BLE001
        pass
    # Does this finished row have a report to reopen? Only the «Hechas» list draws that button, and only it
    # pays for the question — one `task_artifacts` lookup per row. A button that opens nothing is worse than
    # no button, so it is not drawn on a guess: `has_results` is the answer, not an assumption about `kind`.
    reopenable = None
    if scope == "done":
        try:
            from widgets.results import rehydrate as _rehy
            reopenable = _rehy.has_results
        except Exception:  # noqa: BLE001 — no rehydrate module, no buttons; the list still reads
            reopenable = None
    out = []
    for r in rows:
        if reopenable is not None:
            r = {**r, "has_results": bool(reopenable(str(r.get("id") or "")))}
        det = live.get(str(r.get("id") or ""))
        if det:
            r = {**r, "phase": det.get("phase", ""), "note": det.get("note", ""),
                 "pct": det.get("pct", -1), "plan": det.get("plan", []), "total": det.get("total", 0),
                 "done_steps": det.get("done", 0), "steps": det.get("steps", []),
                 "waiting_on": det.get("waiting_on", ""), "ask": det.get("ask", ""),
                 "paused": det.get("paused", False), "silent_s": det.get("silent_s", 0),
                 "considered": det.get("considered", -1), "kept": det.get("kept", -1),
                 "backend": det.get("backend", "")}
        elif r.get("id") in phases:
            r = {**r, "phase": phases[r["id"]]}
        out.append(r)
    return out


def interrupted(entry: dict) -> None:
    """A worker that a RESTART cut in half. Recorded as `failed`, with its own wording (V2-259/rehydrate).

    What must not happen is the thing that used to: the session vanished with the process and NOTHING said
    so — no event, no row, no word to the operator, who kept waiting for an answer that had stopped being on
    its way. A cut task is not a finished one and is not painted as one: `histRow` gives an interrupted row
    its own «✂» precisely so a restart can never read as a success.
    """
    tid = str((entry or {}).get("id") or "").strip()
    if not tid:
        return
    uid = task_uid(tid)
    now = int(time.time())
    if _ts.task_get(uid) is None:
        _ts.task_put({"id": uid, "title": str(entry.get("goal") or ""), "goal": str(entry.get("goal") or ""),
                      "kind": str(entry.get("kind") or "generic"), "mode": "now", "state": "failed",
                      "visible": True, "origin": "voz", "created_at": int(entry.get("started_at") or now),
                      "started_at": int(entry.get("started_at") or 0) or now, "finished_at": now,
                      "outcome": "interrumpido por un reinicio del motor"})
        return
    _ts.task_patch(uid, state="failed", finished_at=now,
                   outcome="interrumpido por un reinicio del motor")


def board_cleared() -> int:
    """«Empezamos de cero»: the reset wipes the operator's board. Returns how many rows went.

    BOTH halves, because both are «work in progress» from where he sits: what already finished, and what the
    reset itself just killed a second ago. Standing commitments (`scheduled`/`recurring`) are deliberately
    left alone — see `tasks_store.tasks_clear`.

    ONLY the reset button does this. The spoken «para todo» keeps the history on purpose: what it cancelled
    must be VISIBLE there as `cancelled`, which is a different thing from starting from zero.
    """
    return _ts.tasks_clear(states=_ts.DONE_STATES + _ts.LIVE_STATES, modes=("now",))


def pruned(max_age_days: float = 30.0, now: float | None = None) -> int:
    """Sleep-time hygiene, injected into the consolidator by `nucleo/loop.py`. See `tasks_store.tasks_prune`.

    Injected rather than imported by the consolidator for the reason the audit of 2026-08-23 fixed once
    already: `memory/` must not reach into `nucleo/`, and a lazy import inside a function is that reach with
    the evidence hidden one line lower. `now` is part of the HOOK's signature (the consolidator passes the
    sweep's clock so a sweep is reproducible), so it is accepted here even though the default is fine —
    a hook whose signature does not match its caller fails silently into the caller's `except`.
    """
    return _ts.tasks_prune(max_age_days, now=now)


# ── scheduled work (V2-005) ──────────────────────────────────────────────────────────────────────────────
#: A parsed schedule's `type` → the task's mode. `once` fires and closes; `interval` and `cron` repeat. The
#: operator reads those as two DIFFERENT lists, and until V2-728 they were one: «enséñame las tareas
#: programadas» opened the things that repeat, with no error to notice it by.
_SCHED_MODE = {"once": "scheduled", "interval": "recurring", "cron": "recurring"}


def scheduled_uid(job_id) -> str:
    """The task id of a scheduled job. Namespaced on its `journal` row id, which is a durable primary key."""
    return f"cron:{str(job_id or '').strip()}"


def scheduled_mirrored(entry: dict) -> None:
    """Keep the `tasks` row of a scheduled job in step with its `journal` row.

    WHY A MIRROR and not a move. The plan for this phase was to move the scheduler's storage onto `tasks`
    outright. It is not worth the risk and the reason is specific: a `journal` row holds the scheduler's own
    WORKING state — the parsed schedule, `fire_count`, `last_fired` — and migrating live rows means migrating
    the operator's standing commitments. The worst failure available here is a reminder that silently stops
    existing, which is exactly what a botched migration produces and exactly what nobody notices until the
    day it fails to sound (V2-121). So the scheduler keeps writing where it works, and this gives the board
    the row it needs. It is the same shape as `errand_mirrored` above, for a different reason.

    The move stays on the table; it is written down in V2-728 as deferred, not as done.
    """
    if not isinstance(entry, dict) or not entry.get("id"):
        return
    d = entry.get("detail") or {}
    sch = d.get("schedule") or {}
    mode = _SCHED_MODE.get(str(sch.get("type") or ""), "scheduled")
    nxt = sch.get("next_run")
    closed = str(entry.get("status") or "pending") != "pending"
    _ts.task_put({
        "id": scheduled_uid(entry["id"]),
        "title": str(d.get("name") or entry.get("title") or ""),
        "goal": str(d.get("prompt") or entry.get("title") or ""),
        "kind": "reminder",
        "mode": mode,
        # A closed ONE-SHOT has done its job; a closed recurring one was cancelled. The list says which.
        "state": ("done" if mode == "scheduled" else "cancelled") if closed else "pending",
        "visible": True,
        # WHO put the clock on it (`scheduler.create(origin=…)`). An appointment's notice says `agenda`, and
        # that is the one value the agenda's own reader filters out — otherwise every meeting would appear
        # twice on the calendar: once as the appointment and once as its own alarm.
        "origin": str(d.get("origin") or "cron"),
        "schedule": {"type": sch.get("type"), "display": sch.get("display") or "",
                     "next_run": int(nxt) if isinstance(nxt, (int, float)) else None,
                     "fire_count": int(d.get("fire_count") or 0)},
        "surface": "voz",
        "created_at": int(entry.get("created") or 0),
        "due_at": int(nxt) if isinstance(nxt, (int, float)) and not closed else 0,
        "finished_at": int(entry.get("updated") or 0) if closed else 0,
    })


def scheduled_forgotten(job_id) -> None:
    """A job deleted outright (not fired, not cancelled) leaves no row behind."""
    _ts.task_forget(scheduled_uid(job_id))


# ── thin reads, so `memory.tasks_store` keeps ONE importer ───────────────────────────────────────────────
# `nucleo/flash/task_recall.py` and `widgets/results/rehydrate.py` both need to read the ledger, and both
# reaching in directly would make the memory boundary a three-caller seam rather than a one-caller one. The
# boundary ratchet (`tests/memory/unit/test_memory_boundary.py`) counts exactly that, and paying it by
# raising its ceiling would be the move its own docstring tells you not to make.
def search(query: str, limit: int = 5) -> list[dict]:
    """Finished commissions this phrase could be about, newest first. Lexical only — never a model."""
    return _ts.task_search(query, limit=limit)


def get(task_id: str) -> dict | None:
    return _ts.task_get(task_id)


def artifacts(task_id: str) -> dict:
    """Every stored part of one task's result, keyed by slot."""
    return _ts.artifacts_of(task_id)


def artifact(task_id: str, slot: str):
    return _ts.artifact_get(task_id, slot)
