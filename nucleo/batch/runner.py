"""The LIST: durable, run one step at a time through the ordinary turn, reported once (V2-771).

Storage is the task table (V2-728): the list is one visible row (`kind="lista"`) and each step a child row
(`parent_id`, hidden — the board shows the commission, not its plumbing). A restart therefore loses nothing:
`resume()` picks up every list that still has pending steps.

Each step runs as an ORDINARY TURN of the text channel (`probe.run_turn(execute=True)`): the Jev brief, the
real prompt, the model, the widgets, the workers — the whole machine, one step at a time, so each step sits
well inside the per-turn limits the unsplit message collided with. All steps share one conversation session,
so step 9 («Anna vacation») is read with steps 1-8 behind it.

Memory is written by THIS module, awaited, step by step — not fire-and-forget like a live turn. The distiller
serialises its calls and falls back to a lossy heuristic when more than two are waiting
(`mem_processor._QUEUE_MAX`); eighteen steps three seconds apart would have landed exactly there.

A step that hands work to a Brain Worker does not block the list: the worker takes its seat in the pool
(two at a time since V2-771, FIFO behind that) and the list moves on. The list's report waits for those
workers, so «I've finished» is never said over work still running (V2-743).

One list at a time (`_LOCK`): a second list queues behind the first instead of interleaving steps with it.
"""
from __future__ import annotations

import asyncio
import secrets
import time

from loguru import logger

#: How long the report waits for the workers a list started. Past it the report goes out anyway and says
#: which ones are still running — a list must never go quiet forever behind one stuck worker.
WORKER_WAIT_S = 45 * 60
_POLL_S = 5.0

_LOCK: asyncio.Lock | None = None
_RUNNING: set[str] = set()


def _lock() -> asyncio.Lock:
    global _LOCK
    if _LOCK is None:
        _LOCK = asyncio.Lock()
    return _LOCK


def _emit(label: str, **extra) -> None:
    try:
        from voice.observer import emit
        emit("brain", label, text=str(extra.pop("text", ""))[:400], role="system",
             extra={"cat": "flash", "engine": "lista", **extra})
    except Exception:  # noqa: BLE001
        pass


def _store():
    from nucleo import tasks
    return tasks.store()


def new_uid() -> str:
    return f"lista:{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}"


def step_id(uid: str, i: int) -> str:
    return f"{uid}#{i:02d}"


def create(text: str, steps: list[dict], *, origin: str = "voz", how: str = "model") -> str:
    """Write the list and its steps. Returns the list's uid."""
    ts = _store()
    uid = new_uid()
    now = int(time.time())
    first = next((s["title"] for s in steps if s.get("title")), "")
    ts.task_put({"id": uid, "title": f"{len(steps)} × {first}"[:120] if first else f"{len(steps)} tareas",
                 "goal": (text or "")[:8000], "kind": "lista", "mode": "now", "state": "pending",
                 "visible": True, "origin": origin, "surface": "voz", "outcome": f"0/{len(steps)}",
                 "created_at": now})
    for i, s in enumerate(steps, 1):
        ts.task_put({"id": step_id(uid, i), "title": s.get("title") or s["say"][:60], "goal": s["say"],
                     "kind": s.get("kind") or "other", "mode": "now", "state": "pending", "visible": False,
                     "origin": "lista", "surface": "voz", "parent_id": uid, "created_at": now})
    ts.artifact_put(uid, "steps", {"how": how, "steps": steps})
    return uid


def steps_of(uid: str) -> list[dict]:
    """The list's step rows in order (their ids sort by position)."""
    return _store().tasks_children(uid)


def outcome_of(r: dict) -> tuple[str, str, list[str]]:
    """(state, note, worker task ids) of one step from the turn's own report.

    `waiting` means a worker is carrying it. `needs_you` — the turn answered with a QUESTION: the list cannot
    answer for him, so the step is left for the report to ask instead of being counted as done."""
    r = r if isinstance(r, dict) else {}
    reply = r.get("reply")
    reply = " ".join(reply) if isinstance(reply, list) else str(reply or "")
    if not r.get("ok", True) or r.get("error"):
        return "failed", str(r.get("error") or "")[:200], []
    if r.get("execute_error") or r.get("executed") == "widget_data_failed":
        return "failed", str(r.get("execute_error") or reply)[:200], []
    tids = [str(t) for t in (r.get("task_ids") or ([r["task_id"]] if r.get("task_id") else [])) if t]
    if tids:
        return "waiting", reply[:200], tids
    if r.get("executed") == "escalate":
        # The portal refused it (id 0): no errand was ever born. Measured on the errands case — the protected-core
        # guard refused a bike comparison and the step, having CALLED escalate, was counted done.
        return "failed", ("not started — " + reply)[:200], []
    if reply.rstrip().endswith(("?", "？")):
        return "needs_you", reply[:300], []
    return "done", reply[:200], []


#: The step's reply ended in a question: is it one the list cannot answer for him, or a courtesy offer?
#: Measured on the first live run of his demo (2026-09-25): «Got it, Richard — … I'll keep all of that in mind.
#: Should I…?» and «Noted… Anything you want me to dig up?» — two steps DONE, reported as needing him because
#: the reply ended in «?». A question mark is punctuation, not a verdict; Jev reads what the question is FOR.
_NEEDS_KEY = "step_reply"
_NEEDS_INSTRUCTIONS = ("The assistant was given ONE task and this is its reply. Can the task be finished "
                       "without the user answering the reply's question?")
_NEEDS_CRITERIA = {
    "needs_answer": "No: the reply asks which one, asks for a missing detail, or asks permission before acting — "
                    "nothing was done yet",
    "done": "Yes: the reply says the task is done or noted; its question only offers further help or chats",
}


async def reply_needs_him(task: str, reply: str) -> bool:
    """True when a question-ending reply is a real question back (a Jev trip, in a thread). Unsure or no answer
    → True, the honest side: the report asks him, it never claims a step it did not see done."""
    try:
        from nucleo import jev
        v = await asyncio.to_thread(jev.choose_sync, _NEEDS_KEY, f"TASK: {task[:600]}\nREPLY: {reply[:600]}",
                                    instructions=_NEEDS_INSTRUCTIONS, criteria=_NEEDS_CRITERIA,
                                    question_id="list-step-reply")
    except Exception:  # noqa: BLE001
        v = None
    return not (v and v.get("choice") == "done" and float(v.get("confidence") or 0) >= 0.7)


#: Step kinds that exist to CHANGE something (the split's own label). A turn for one of these that executed
#: nothing did not do it, whatever its reply says. Measured on the second live run of his demo (2026-09-25):
#: «Create a calendar event … “Call with accountant”» → «I'll put that on your agenda now.» and no call, twice in
#: seven, with nothing open on the canvas — so neither the promise detector (a phrase table that knew none of
#: those replies) nor the verdict (`catalog_widget=none` 1.00) could repair it, and the list counted it DONE.
ACTION_KINDS = frozenset({"agenda", "reminder", "message", "task"})


def acted(r: dict) -> bool:
    """Did the turn EXECUTE anything? The turn's own report, never its words: a tool call, a tag, an execution
    record or a worker. A lane that answered without the model (rename, action map) reports its own action."""
    r = r if isinstance(r, dict) else {}
    if r.get("tool_calls") or r.get("tags") or r.get("executed") or r.get("task_ids") or r.get("task_id"):
        return True
    return str(r.get("action") or "chat") not in ("chat", "")


# A step runs with `lists=False`, which also keeps it from draining `brain_notes`: those notes are the
# operator's (a worker finishing, a refusal) and belong to HIS next turn. Measured on the errands case: the step
# after a refused search swallowed the refusal note and answered about it — «Las bicis ya están en marcha…
# no puedo cambiarme por dentro» — to a step that only set a standing rule, and was reported as needing him.
async def _turn(turn, text: str, sid: str) -> dict:
    try:
        return await turn(text, sid=sid, ingest=False, execute=True, lists=False)
    except Exception as e:  # noqa: BLE001 — one broken step never takes the list down
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _live_workers() -> dict[str, str]:
    """{durable commission uid: worker id} for every worker the dispatcher knows right now.

    Keyed by the DURABLE uid, not the worker id: a relay (quota → stand-in) is a NEW worker id for the SAME
    commission and inherits its uid. Measured on the errands case, run 4: the trainers search was relayed while the
    restaurant step ran, the new id looked like «a worker this step started», and the restaurant step — which had
    only SAID «voy con el restaurante» — was counted as waiting on somebody else's worker."""
    try:
        from nucleo import dispatch
        out = {}
        for x in dispatch.active_sessions():
            if x.get("id") is None:
                continue
            out[str(x.get("uid") or x.get("id"))] = str(x.get("id"))
        return out
    except Exception:  # noqa: BLE001
        return {}


#: How long after a step's turn a worker it started may still be registering (the escalation travels the bus).
_SETTLE_S = 1.5


async def _run_step(uid: str, row: dict, turn, ingest) -> None:
    ts = _store()
    ts.task_patch(row["id"], state="running", started_at=int(time.time()))
    _emit("📋 lista: paso", text=row["goal"], step=row["id"])
    before = _live_workers()
    r = await _turn(turn, row["goal"], uid)
    # The workers THIS step started, whatever door it used. Measured on the errands case: a product search went
    # through the listings lane, which starts its worker inside and reports only what it said — so the step read
    # DONE and the list would have reported over a worker still searching. The dispatcher's own registry, before
    # and after, says it without trusting any one path to report its ids.
    await asyncio.sleep(_SETTLE_S)
    after = _live_workers()
    started = sorted(after[k] for k in set(after) - set(before))
    if started and isinstance(r, dict) and not (r.get("task_ids") or r.get("task_id")):
        r = {**r, "task_ids": started}
    # Memory, awaited — see the module note. A step that failed still said something true about him. Written
    # BEFORE the action check because, for a REMINDER, remembering is the action: «Remember these future
    # responsibilities even when they are not on the calendar» was stored whole (four renewals) and the step
    # was still failed «no action taken», and the report told him «I couldn't do: Personal reminders» (his demo
    # run, 2026-09-26). An agenda or message step still needs its call; memory never stands in for those.
    wrote = 0
    try:
        got = await ingest(row["goal"])
        wrote = int((got or {}).get("atoms") or 0) if isinstance(got, dict) else 0
    except Exception as e:  # noqa: BLE001
        logger.warning(f"lista {uid}: memory ingest failed on {row['id']}: {e!r}")
    kind = str(row.get("kind") or "")
    if kind in ACTION_KINDS and outcome_of(r)[0] == "done" and not acted(r) and not (kind == "reminder" and wrote):
        # ONE retry, in a fresh session: the list's own window now holds the claim («Adding it now»), and a
        # model that reads its own claim answers «already done». Still nothing → failed, and the report says so.
        _emit("📋 lista: paso sin acción — reintento", text=str(r.get("reply") or "")[:200], step=row["id"])
        r = await _turn(turn, row["goal"], f"{uid}:{row['id'][-2:]}")
        if outcome_of(r)[0] == "done" and not acted(r):
            r = {"ok": False, "error": f"no action taken — «{str(r.get('reply') or '')[:160]}»"}
    state, note, tids = outcome_of(r)
    if state == "needs_you" and not await reply_needs_him(row["goal"], note):
        state = "done"
    fields = {"state": "running" if state == "waiting" else ("waiting" if state == "needs_you" else state),
              "outcome": (f"workers:{','.join(tids)} " if tids else "") + f"[{state}] {note}"}
    if state in ("done", "failed"):
        fields["finished_at"] = int(time.time())
    ts.task_patch(row["id"], **fields)
    _emit(f"📋 lista: paso {state}", text=note, step=row["id"])


def _worker_state(tid: str) -> str:
    """'' while the commission is alive; its ending otherwise.

    The DURABLE row speaks first once it is closed. A relay (`nucleo/workers/relay.py`) continues the same
    commission under a NEW worker id and inherits the row, so the first worker's RAM record stays `relevada`
    for good — measured on the errands case: the row said `failed` at 20:30 and the list, reading the RAM
    record, would have waited its whole 45 minutes. The RAM record answers while the row is still open (the
    row does not track `running`)."""
    try:
        from nucleo import dispatch, tasks as _tasks
        row = _store().task_get(_tasks.task_uid(tid)) or {}
        st = str(row.get("state") or "")
        if st in ("done", "failed", "cancelled"):
            return st
        rec = dispatch.get_record(tid)
        if rec is not None:
            st = str(getattr(rec, "status", "") or "")
            return "" if st in ("queued", "running", "relevada", "") else st
        if row:
            return ""                     # open row, no live record yet (queued behind the pool)
        return "done"                     # nothing anywhere: never wait forever on a ghost
    except Exception:  # noqa: BLE001
        return "done"


async def _wait_workers(uid: str, *, wait_s: float = WORKER_WAIT_S, poll_s: float | None = None) -> None:
    ts = _store()
    poll_s = _POLL_S if poll_s is None else poll_s
    deadline = time.time() + wait_s
    while True:
        pending = 0
        for row in steps_of(uid):
            out = str(row.get("outcome") or "")
            if row.get("state") != "running" or not out.startswith("workers:"):
                continue
            tids = out.split(" ", 1)[0][len("workers:"):].split(",")
            states = [_worker_state(t) for t in tids if t]
            if all(states):
                ok = all(s == "done" for s in states)
                ts.task_patch(row["id"], state="done" if ok else "failed", finished_at=int(time.time()),
                              outcome=out.replace("[waiting]", "[done]" if ok else "[failed]"))
            else:
                pending += 1
        if not pending or time.time() >= deadline:
            return
        await asyncio.sleep(poll_s)


def summary(uid: str) -> dict:
    rows = steps_of(uid)
    by = {"done": [], "failed": [], "needs_you": [], "running": [], "pending": []}
    for r in rows:
        st = str(r.get("state") or "pending")
        key = "needs_you" if st == "waiting" else st
        by.setdefault(key, []).append(r)
    return {"n": len(rows), **{k: v for k, v in by.items()}}


def report_text(uid: str) -> str:
    """ONE report, counts first, then only what he has to know: what failed, what needs him, what is still
    running. Never a step-by-step narration of what went fine."""
    from i18n import langs
    L = langs.current_language()
    s = summary(uid)
    parts = [L.list_done.format(ok=len(s["done"]), n=s["n"])]
    if s["failed"]:
        parts.append(L.list_failed.format(items="; ".join(r["title"] for r in s["failed"][:6])))
    if s["needs_you"]:
        parts.append(L.list_needs_you.format(items="; ".join(
            str(r.get("outcome") or "").split("] ", 1)[-1][:160] for r in s["needs_you"][:4])))
    if s["running"]:
        parts.append(L.list_still_running.format(n=len(s["running"])))
    return " ".join(parts)


async def run(uid: str, *, turn=None, ingest=None, notify=None, worker_wait_s: float = WORKER_WAIT_S) -> dict:
    """Run every pending step of a list in order, wait for its workers, close it and report. Idempotent over a
    restart: steps already done are skipped."""
    if turn is None:
        from nucleo.flash.probe import run_turn as turn
    if ingest is None:
        from nucleo.memory_agent import ingest_utterance

        async def ingest(text):
            return await ingest_utterance(text, role="operator")
    if notify is None:
        from voice.proactive import notify
    if uid in _RUNNING:
        return {}
    _RUNNING.add(uid)
    ts = _store()
    try:
        async with _lock():
            ts.task_patch(uid, state="running", started_at=int(time.time()))
            _emit("📋 lista: empieza", text=uid)
            for row in steps_of(uid):
                if row.get("state") == "pending":
                    await _run_step(uid, row, turn, ingest)
                    s = summary(uid)
                    ts.task_patch(uid, outcome=f"{len(s['done'])}/{s['n']}")
        await _wait_workers(uid, wait_s=worker_wait_s)
        s = summary(uid)
        text = report_text(uid)
        # Closed once reported, even with workers still out: they are rows of their own on the board and each
        # announces its own ending — a list left `running` would be resumed, and REPORTED, a second time after
        # the next restart.
        ts.task_patch(uid, state="failed" if s["failed"] else "done",
                      outcome=f"{len(s['done'])}/{s['n']} · {text}"[:400], finished_at=int(time.time()))
        _emit("📋 lista: terminada", text=text)
        try:
            await notify("lista", text)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"lista {uid}: report not delivered: {e!r}")
        return s
    finally:
        _RUNNING.discard(uid)


def resume() -> list[str]:
    """Lists that a restart interrupted, relaunched. Called once at boot; returns the uids it restarted.
    A step left `running` by the restart is run again — its turn never reported, so nothing claims it."""
    ts = _store()
    out = []
    for uid in [r["id"] for r in ts.tasks_of_kind("lista", ("pending", "running"))]:
        for st in steps_of(uid):
            if st.get("state") == "running" and not str(st.get("outcome") or "").startswith("workers:"):
                ts.task_patch(st["id"], state="pending")
        try:
            asyncio.get_running_loop().create_task(_after(RESUME_DELAY_S, run(uid)))
            out.append(uid)
        except RuntimeError:
            break
    return out


#: A resumed list waits for the engine to finish booting (memory cache, widgets, the dispatcher) before its
#: first step runs — the lifespan calls `resume()` well before the first turn could.
RESUME_DELAY_S = 20.0


async def _after(delay: float, coro):
    await asyncio.sleep(delay)
    return await coro
