"""nucleo/acts/errand.py — the errand door (refactor2710-06 T-03, moved from nucleo/flash/escalate.py; V2-004/V2-007).

The ONE gateway every escalation passes through: it records the intent (live status can say «still on it») and
publishes `escalate.requested` on the bus; `nucleo.dispatch` runs the worker and delivers through `voice/proactive`
and a `[SISTEMA]` note, then calls `finish()`. Below it, `errand_target`: which errand his words are for.
"""
from __future__ import annotations

import time

from loguru import logger

_tasks: dict[int, dict] = {}      # id → {request, started_at, done, summary}
# Ids are per-process (F5): anything DURABLE keyed on them composes `runtime_ids.boot_id()` in (the `32c7dc6` wipe).
from nucleo.runtime_ids import next_seq as _next_seq, reset_seq as _reset_seq
_MAX = 12                          # keep the most recent; discard old ones (never grows without limit)


def _emit_bus(topic: str, payload: dict) -> None:
    """Publish to the nervous system in a loop-agnostic way (FlashBrain runs in LiveKit's job thread)."""
    try:
        import bus
        bus.emit_sync(topic, payload)
    except Exception:
        pass


# System notes that PREPEND the turn (`voice/brain_notes.py`) are CONTEXT, never what he asked for — yet every
# escalation path falls back to the turn's text, notes included (V2-118: three of seven tasks had «[SISTEMA] … Tarea
# completada» as their objective). Cleaned HERE, the single gateway, so a new caller inherits it.
_SYSTEM_NOTE_PREFIX = "[SISTEMA]"


def strip_system_notes(text: str) -> str:
    """The turn's text without the `[SISTEMA] …` notes glued in front of it; "" when there were ONLY notes (a note
    never becomes work). A note is a BLOCK, not a line (session 651cd038: the late-recall note lists what it
    recovered, and its second line became the goal of a worker nobody asked for); the boundary is the blank line
    `nucleo.py` puts between the notes and his words, which `brain_notes.push` never puts inside a note."""
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


def _refuse(req: str, reason: str) -> None:
    """La negativa VIAJA: al operador por la vía proactiva (que ya sabe hablar y ya sabe degradar a nota
    escrita si no hay voz) y a la línea de tiempo, para que «no pasó nada» nunca sea la única evidencia."""
    try:
        from voice.observer import emit
        emit("task", "blocked", role="system", text=req[:120],
             extra={"reason": "el núcleo y el motor no se modifican desde la voz ni el chat"})
    except Exception:  # noqa: BLE001
        pass
    try:
        import asyncio

        from voice import proactive
        asyncio.get_running_loop().create_task(proactive.notify("zaelar", reason))
    except Exception:  # noqa: BLE001 — sin loop (tests, arranque) la fila de la timeline ya deja constancia
        pass
    logger.info(f"escalate: RECHAZADA — pide modificar el motor: {req[:80]}")


def escalate_to_slowbrain(request: str, *, context: dict | None = None) -> int:
    """Queue the INTENT of a SlowBrain turn for `request`. Returns a task id. STUB in V2-004:
    records + publishes `escalate.requested`; SlowBrain executes it asynchronously starting in V2-006/V2-007."""
    req = strip_system_notes(request)
    if not req:
        # Only system notes: he asked for nothing, so there is no task (it was the worker chasing the worker).
        return 0
    # THE CORE IS NOT MODIFIED (V2-655), checked here, the one portal, before any id exists; the dev channel is ours.
    ctx0 = dict(context or {})
    if ctx0.get("kind") != "dev":
        from nucleo import protected_core
        if protected_core.touches_the_engine(req):
            _refuse(req, protected_core.refusal(req))
            return 0
    # A CAPABILITY NO CARD DECLARES IS NOT AN ERRAND (V2-807 T-16): a worker cannot add a feature to the product.
    try:
        from nucleo.flash import capability_gap as _gap
        if _gap.refuses(req, ctx0):
            _gap.refuse(req)
            logger.info(f"escalate: NOT started — asks for a capability no card declares: {req[:80]}")
            return 0
    except Exception as e:  # noqa: BLE001 — the gate may never break the portal
        logger.debug(f"escalate: capability gate skipped: {e!r}")
    # A QUESTION IS NOT THEATRE (V2-655): a turn that ASKED permission aloud has no order yet — it is parked.
    asked = strip_system_notes(str(ctx0.get("asked") or ""))    # our own notes' «¿La hago?» is nobody's offer
    if asked and not ctx0.get("confirmed"):
        from nucleo.flash import clarifying as _clar
        if _clar.asks_permission(asked) and ctx0.get("derived"):
            # The model called nothing and the reply asked him: a request derived from his words waits for his yes.
            _emit_bus("escalate.held", {"request": req, "asked": asked[:200], "ts": time.time()})
            logger.info(f"escalate: NOT started — derived from his words while the reply asks him: {req[:70]}")
            return 0
        if _clar.asks_permission(asked) and not _reasks_a_parked_errand(asked, req):
            try:
                from nucleo.dispatch import confirm as _dc
                _dc.remember_offer(req, context=ctx0, question=asked.strip()[:200])
            except Exception:  # noqa: BLE001
                logger.warning("escalate: no pude aparcar el ofrecimiento; NO lo lanzo por las bravas")
            _emit_bus("escalate.offered", {"request": req, "asked": asked[:200], "ts": time.time()})
            logger.info(f"escalate: APARCADA — el turno pidió permiso: {req[:70]}")
            return 0
    tid = _next_seq("escalate.task")
    _tasks[tid] = {"request": req[:200], "started_at": time.time(), "done": False, "summary": ""}
    if len(_tasks) > _MAX:
        for k in sorted(_tasks)[: len(_tasks) - _MAX]:
            del _tasks[k]
    ctx = dict(context or {})
    # TRACEABILITY (V2-044): the bus does NOT copy the asyncio context, so the turn's trace travels in the payload.
    if "trace" not in ctx:
        try:
            from voice import trace as _trace
            _t = _trace.current()
            if _t:
                ctx["trace"] = _t
        except Exception:
            pass
    # …and so does the SCREEN that asked (V2-792), for the same reason: what the errand opens later goes back there.
    if "origin_dev" not in ctx:
        try:
            from voice import screens as _screens
            _o = _screens.origin_of({"trace": ctx.get("trace", "")})
            if _o:
                ctx["origin_dev"] = _o
        except Exception as e:  # noqa: BLE001 — the errand still starts; its cards then open on the last screen
            logger.debug(f"escalate: no screen origin for the errand: {e!r}")
    from nucleo import consequence as _consequence
    if not _consequence.passes("worker.spawn", request=req[:200], kind=str(ctx.get("kind") or "")):
        return tid
    _emit_bus("escalate.requested", {"id": tid, "request": req, "context": ctx, "ts": time.time()})
    return tid


def _reasks_a_parked_errand(asked: str, req: str) -> bool:
    """Is the permission question in the reply the one an errand ALREADY PARKED is waiting on — so it offers that
    errand, not `req`? (three-tasks-at-once ES, 2026-10-11 02:04: «…Y lo otro: el juego de plataformas… ¿Te lo
    monto?» re-asked the parked game; parking the turn's other errand under it hid the game behind a second,
    newer «offer», and his «Sí, móntalo» was judged against the wrong question.) The yardstick is the one every
    door reads, `named_errand.named`, over the parked errands alone."""
    try:
        from nucleo.turn import errands_of_a_turn as _eot, named_errand as _ne
        parked = [e for e in _ne.known() if e["parked"]]
        hits = _ne.named(asked, parked) if parked else []
        return any(not _eot.same_errand(req, e["request"]) for e in hits)
    except Exception as e:  # noqa: BLE001 — the safe side is today's rule: park it
        logger.debug(f"escalate: parked errands unreadable — {type(e).__name__}: {e}")
        return False


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


# ── which errand his words are for: the brief's `errand_target` (refactor2710-06 T-03) ────────────────────────────
# Three arms leave the turn with no verdict of their own: a message to a cluster peer, an injection into the running
# errand and the cluster's objective. The brief answers once; each arm reads it ASYMMETRICALLY
# (`nucleo.turn.verdicts.against_the_model`): agreeing runs, a sure contrary verdict vetoes, an unsure one asks which,
# and no verdict (an old brief, no worker running) keeps the arm's own deterministic route — never a new question.
TARGET_KEY = "errand_target"
_TARGETS = (
    ("running_errand", "his words are for the errand that is RUNNING now: a correction, a detail, a «yes» it asked for"),
    ("cluster_peer", "his words are a message for a PEER of the cluster (another agent or person in it)"),
    ("cluster_objective", "his words change the cluster's shared OBJECTIVE"),
    ("none", "his words are for none of these: a new order, a question, small talk"),
)
_ARM_TARGET = (("send_to_worker", "running_errand"), ("cluster_send", "cluster_peer"),
               ("set_cluster_objective", "cluster_objective"))


def target_question(_ctx=None) -> dict:
    """The brief's question: which errand (if any) his words are for."""
    return {"instructions": "Which ongoing errand, if any, are the operator's words addressed to?",
            "criteria": dict(_TARGETS)}


def target_allows(brief, tool: str) -> str:
    """`run` · `veto` · `consent.ASK_WHICH` for `tool`'s call, by the brief's `errand_target`."""
    from nucleo.turn import verdicts as _v
    claimed = dict(_ARM_TARGET).get(str(tool or ""), "")
    return _v.against_the_model(brief, TARGET_KEY, lambda choice: str(choice) == claimed) if claimed else _v.RUN
