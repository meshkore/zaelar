"""nucleo/flash/escalate.py — FlashBrain → SlowBrain escalation (V2-004 · T64; REAL escalation closed in V2-007 · T87).

When a turn needs memory/tools/reasoning, FlashBrain calls this seam (via function-calling, not a text tag —
language-agnostic; see `router.py`). It records the intent (so live status can say "I'm still working on it, give
me a little time") and **publishes an `escalate.requested` event on the `bus/`**. Since V2-007 the circuit is
CLOSED: `nucleo/dispatch.run_listener` consumes that event, dispatches the task asynchronously to worker agents
(web/code/generic), and DELIVERS the result through `voice/proactive` (voice+UI) + a `[SISTEMA]` note
(`voice/brain_notes`) — the same circuit as always —, then calls `finish()`. Hermes does NOT run (Hermes is
buried in V2-009).
"""
from __future__ import annotations

import time

_tasks: dict[int, dict] = {}      # id → {request, started_at, done, summary}
# Task ids come from the process-identity owner (F5, 2026-08-23). The counter itself is still per-process —
# that is fine for a RAM registry — but anything DURABLE keyed on these ids must compose `runtime_ids.boot_id()`
# in, or it collides with the previous run's ids (the sheet-wipe defect of `32c7dc6`).
from nucleo.runtime_ids import next_seq as _next_seq, reset_seq as _reset_seq
_MAX = 12                          # keep the most recent; discard old ones (never grows without limit)


def _emit_bus(topic: str, payload: dict) -> None:
    """Publish to the nervous system in a loop-agnostic way (FlashBrain runs in LiveKit's job thread)."""
    try:
        import bus
        bus.emit_sync(topic, payload)
    except Exception:
        pass


# System notes that PREPEND the turn (`voice/brain_notes.py`): async worker results, file uploads, Whisper repairs.
# They are CONTEXT for the response and never part of what the operator asked for — both channels say so in those
# exact words in their own code, and store `operator_text` precisely for this purpose.
#
# And yet they still reached here (V2-118 round 2, 2026-08-18): ALL escalation paths have a fallback, «if the
# model did not fill in `request`, use the turn's text», and that text ALREADY has the note attached in front. In
# the run's task log: of seven tasks, THREE had «[SISTEMA] Brain worker · Tarea completada: …» as their objective
# — in other words, a worker launched to «make» the delivery message from the previous worker. It costs money,
# pollutes the live-task count, and reads as a meaningless objective in the master.
#
# It is cleaned HERE rather than in each fallback because this is the single gateway through which all escalation
# passes: a new call site inherits the cleanup without having to remember it.
_SYSTEM_NOTE_PREFIX = "[SISTEMA]"


def strip_system_notes(text: str) -> str:
    """The turn's text without the `[SISTEMA] …` notes glued in front of it. Returns an empty string when there
    were ONLY notes — the caller decides what to do with that; what must never happen is that a note becomes work.

    A note is a BLOCK, not a line (2026-09-01, operator session 651cd038). This function used to skip only the
    lines that literally start with the prefix, and the late-recall note does not: it announces itself on line one
    and then lists what it recovered.

        [SISTEMA] Durable memory arrived late for the question «…». This is what it had:
        · The city is called Valls (pronounced 'Valch').
        · The operator prefers using only their first name…

    Line one was stripped and the rest survived, so the errand's goal became «· The city is called Valls…» and the
    operator watched a worker called «Cita en Valls» open a browser he had not asked for, while he was asking about
    second-hand catamarans. Stripping only the first line of a multi-line note is worse than not stripping at all:
    what is left has lost the `[SISTEMA]` marker that would have let anyone downstream recognise it.

    The boundary is the blank line that `nucleo.py` puts between the notes and the operator's words
    (`text = "\n".join(notes) + "\n\n" + text`), and `brain_notes.push` keeps a note free of blank lines of its own
    precisely so that boundary means one thing."""
    lines = (text or "").split("\n")
    i = 0
    in_note = False
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(_SYSTEM_NOTE_PREFIX):
            in_note = True
        elif not line:
            i += 1
            if in_note:
                break          # the blank line that separates the notes from what the operator said
            continue
        elif not in_note:
            break              # the operator's own words start here
        i += 1                 # a continuation line: still the note talking
    return "\n".join(lines[i:]).strip()


def escalate_to_slowbrain(request: str, *, context: dict | None = None) -> int:
    """Queue the INTENT of a SlowBrain turn for `request`. Returns a task id. STUB in V2-004:
    records + publishes `escalate.requested`; SlowBrain executes it asynchronously starting in V2-006/V2-007."""
    req = strip_system_notes(request)
    if not req:
        # There were only system notes: the operator asked for nothing, so there is no task. Previously this
        # was precisely the worker-chasing-the-worker.
        return 0
    tid = _next_seq("escalate.task")
    _tasks[tid] = {"request": req[:200], "started_at": time.time(), "done": False, "summary": ""}
    if len(_tasks) > _MAX:
        for k in sorted(_tasks)[: len(_tasks) - _MAX]:
            del _tasks[k]
    ctx = dict(context or {})
    # TRACEABILITY (V2-044): the bus does NOT copy the asyncio context → the escalating turn's trace travels IN the
    # payload; dispatch seals it in the SessionRecord and the entire worker cycle remains linked to the utterance.
    if "trace" not in ctx:
        try:
            from voice import trace as _trace
            _t = _trace.current()
            if _t:
                ctx["trace"] = _t
        except Exception:
            pass
    _emit_bus("escalate.requested", {"id": tid, "request": req, "context": ctx, "ts": time.time()})
    return tid


def finish(tid: int, summary: str = "") -> None:
    """Mark an escalation as resolved (the SlowBrain return will call this in V2-007)."""
    t = _tasks.get(tid)
    if t:
        t["done"] = True
        t["summary"] = (summary or "").strip()[:160]
        _emit_bus("escalate.done", {"id": tid, "summary": t["summary"]})


def pending() -> list[dict]:
    """In-flight (unresolved) escalations, oldest first, with elapsed seconds."""
    now = time.time()
    return [{"id": tid, "request": _tasks[tid]["request"], "secs": int(now - _tasks[tid]["started_at"])}
            for tid in sorted(_tasks) if not _tasks[tid]["done"]]


def summary_line() -> str:
    """A compact line for FlashBrain's live-status block, or '' if nothing is in flight."""
    p = pending()
    if not p:
        return ""
    bits = [f'«{t["request"][:60]}» (llevas {t["secs"]}s)' for t in p]
    return ("TAREAS DE FONDO EN CURSO (el cerebro profundo las está resolviendo; si el operador pregunta, dilo "
            "con naturalidad, NO reinicies ni digas que ya está): " + "; ".join(bits))


def reset() -> None:
    """Clear the registry (tests)."""
    _tasks.clear()
    _reset_seq("escalate.task")
