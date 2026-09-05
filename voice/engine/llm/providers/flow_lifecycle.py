"""The FLOW LIFECYCLE of a voice turn (V2-090 · V2-096 · V2-113 · V2-116 · V2-123).

Extracted from `providers/nucleo.py` on the 2026-09-05 ratchet pass (the file had grown past its ceiling; the
ratchet asks for a module, never a taller ceiling). One closed cluster: when a trace is opened or adopted, when
a resolved fragment chain keeps its trace in grace, when a finished turn merges into a live task's flow, and
when a flow closes — plus the deferred-close queue the TTS drains. `nucleo.py` re-exports every name, so callers
and tests keep saying `nucleo._merge_target` / `nucleo._PENDING_FLOW_CLOSES` (the dict is the SAME object — the
cluster only ever mutates it, never rebinds it, which is what makes the re-export safe; V2-555).
"""
from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:                  # runtime import would be circular; the annotations are strings
    from voice.engine.llm.providers.nucleo import NucleoLLM

from widgets import confirm as _wconfirm

# How long the trace of an already resolved chain remains “in grace”, so the next fragment of the SAME
# phrase adopts it instead of opening a new flow (V2-116). 3 s comfortably covers the real pauses measured within
# a phrase (V2-096: p50 2.3 s) without joining two distinct requests: once the window passes, new topic = new flow,
# as always.
_CHAIN_GRACE_S = float(os.getenv("ZAELAR_CHAIN_GRACE_S", "3.0"))


def _begin_or_adopt_trace(brain: "NucleoLLM", text: str, first_turn: bool) -> None:
    """Decide whether this turn opens a NEW trace or ADOPTS the one from a partially completed fragment chain (V2-096
    addendum, 2026-08-15). LiveKit closes a turn for EACH final STT segment, so a long sentence spoken without
    pauses used to open a new flow for each fragment — each cancelled by the next (barge-in) until the last one
    completed. The ACCUMULATOR (`nucleo/flash/accumulator.py`) already knows whether a chain is in progress
    (`.pending()`): while it has one, this turn is that same sentence growing → adopt its trace instead of opening
    a new one, without repeating the completeness judgment here (that is its job). A turn that starts a new chain
    (empty buffer) opens a trace with `begin()` as usual, and that id becomes the chain's until it is resolved
    (`brain._acc_trace_id`, cleared by the caller when `offer()` returns "act").

    ⚠️ THAT ALONE IS NOT ENOUGH, and it broke again on 2026-08-18 (session b403c979, V2-116). Adoption relied
    ENTIRELY on the accumulator having the chain open (`.pending()`), that is, on the LEXICAL layer
    (`segmenter.looks_incomplete`) correctly deciding that "this is incomplete". One false "complete" breaks the
    chain and therefore the flow: measured against that session's five real STT finals,
    `looks_incomplete("Mira, lo que quiero es")` returns **False**—a clause hanging from the copula "es" that
    requires a complement not yet spoken—so the accumulator RELEASES it, `_acc_trace_id` is cleared
    (the "act" branch), and the next fragment opens a new flow. In production, FOUR corr_ids came from one
    sentence, each cancelling the previous one through barge-in.

    FLOW continuity cannot depend on correctly judging sentence completeness: they are two different questions,
    different, and the flow is the skeleton ("any continuous action that may last minutes is associated with a
    flow", the operator's rule). Therefore, when a chain resolves, its trace is not discarded: it remains in GRACE
    for a few seconds (`_CHAIN_GRACE_S`), and a turn arriving within that window ADOPTS it. This is structural and
    cheap—no word lists, no LLM, no latency—and fails on the safe side: at most it joins two nearly consecutive
    sentences into one flow, which is MUCH less harmful than splitting a hesitant sentence into four.
    The root cause (the lexical layer's false "complete", which also burns an entire prompt and leaves a turn
    cancelled) is documented and reproduced in V2-116; changing those lists requires measurement against the corpus
    prepared by V2-095, not a guess-and-check patch.

    Separate function (not inline in `_run_inner`) so it can be tested WITHOUT a real LiveKit stream — see
    `tests/voice/unit/providers/test_nucleo_trace_merge.py`."""
    from voice import trace as _trace
    if first_turn:
        _trace.begin(text, origin="kickoff")
        return
    if getattr(brain, "_acc", None) is not None and brain._acc.pending() and brain._acc_trace_id:
        _trace.adopt(brain._acc_trace_id)
        return
    grace_tid, grace_ts = getattr(brain, "_chain_grace", ("", 0.0))
    if grace_tid and (time.time() - grace_ts) <= _CHAIN_GRACE_S:
        brain._acc_trace_id = grace_tid
        _trace.adopt(grace_tid)
        return
    brain._acc_trace_id = _trace.begin(text, origin="turno")


def _resolve_acc_chain(brain: "NucleoLLM") -> None:
    """A fragment chain has just been RESOLVED (`offer()` returned "act"): its trace stops being active but
    enters GRACE instead of being discarded, so the next fragment of the same phrase adopts it
    (`_begin_or_adopt_trace`) instead of opening a new flow.

    It exists as a function —rather than two lines inside `_run_inner`— so the test can exercise THE SAME
    code that runs in production. A test that re-implements the caller’s accounting can pass while production does
    something else, which is exactly the failure mode V2-116 is meant to close."""
    if getattr(brain, "_acc_trace_id", ""):
        brain._chain_grace = (brain._acc_trace_id, time.time())
    brain._acc_trace_id = ""


# Tools that CONTROL a running task rather than start something else. A turn that only used these (or none at
# all) is a turn about the task already in flight — see `_merge_target`.
_WORKER_CONTROL_TOOLS = frozenset({"send_to_worker", "stop_worker", "answer_worker", "recall", "need_capability"})


def _merge_target(tid: str, live_traces, turn_tools, just_escalated: bool = False) -> str:
    """Pure decision (V2-123): which LIVE task's flow should absorb this finished turn, or '' for none.

    The gap this closes was reported with a screenshot: while a worker searched for a guitar, "sí, muéstramelo todo
    en tiempo real" and the agent's reply to it opened a SEPARATE flow, because V2-090's merge only fires when the
    model happens to call `send_to_worker` (its handler is where `resolve_sessions` gets consulted). A follow-up
    the model answers conversationally — the most natural thing an operator says while waiting — matched nothing
    and split the thread. The operator's rule is the opposite: "siempre que nos estemos refiriendo a la misma
    tarea… todo tiene que ir en un mismo hilo cronológico".

    Deliberately NOT text matching. Both resolvers this module could have reused are wrong for attribution, and
    that mattered more than it looks: `dispatch.resolve_sessions` is loose ON PURPOSE ("mejor parar de más que
    dejar zombies") so with one live task it returns it for ANY wording — precision it does not actually have;
    `find_duplicate` is strict (60% content-word overlap) and "muéstramelo en tiempo real" shares zero words with
    "busca una guitarra zurda", so it would reject the very case this exists for. What IS solid evidence is state
    we already hold: exactly one task is running, and this turn started nothing else.

    Guards, each closing a way this could attribute wrongly:
      · `just_escalated` — this turn launched a NEW task; by definition its own thread (V2-113's signal, reused).
      · `tid` itself live — this trace already IS a task; it is not a loose turn looking for a home.
      · exactly ONE candidate — with several tasks running, which one a bare "¿cómo va?" refers to is a guess, and
        the standing rule since V2-090 is that a stray extra flow beats guessing.
      · tools outside `_WORKER_CONTROL_TOOLS` — putting on music or opening an unrelated widget is a turn about
        something else, whatever else is running.

    KNOWN false merge, accepted with eyes open: a purely conversational request that uses no tool ("cuéntame un
    chiste") while one task runs lands in that task's thread. The trade is deliberate — the operator asked for a
    COMPLETE thread, the split is the reported bug, and the mis-attribution is bounded to one live task's lifetime
    and stays visible (the board paints the `+N` chip). The upgrade that removes the guesswork is the model
    DECLARING continuation (V2-105's recommended design); that needs a tool-schema change and its own measurement,
    and it is not a reason to keep splitting threads meanwhile."""
    if not tid or just_escalated:
        return ""
    live = [t for t in (live_traces or []) if t]
    if tid in live:
        return ""
    candidates = [t for t in live if t != tid]
    if len(candidates) != 1:
        return ""
    if any(t not in _WORKER_CONTROL_TOOLS for t in (turn_tools or ())):
        return ""
    return candidates[0]


def _flow_should_close(tid: str, acc_trace_id: str, confirm_trace_ids, has_live_worker: bool,
                        just_escalated: bool = False) -> bool:
    """Pure decision: should THIS trace's flow close now? Factored out so it is comprobable without the observer/
    dispatch/confirm modules (see `tests/voice/unit/providers/test_nucleo_trace_merge.py`).

    A plain conversational turn never gets its own explicit close from anywhere else — only a worker-spawned flow
    does (`dispatch.py`'s `_run_session` finally block). Without this, the master can only guess "is this flow
    still active?" from RECENCY (`last_ms` within a window), which is wrong the instant a turn finishes: a
    completed kickoff/reply looks identical to a genuinely stuck one until the window expires minutes later —
    reported live by the operator ("he reiniciado el sistema... pero hay siete procesos activos").

    `just_escalated` (V2-113) closes a STRUCTURAL race, not an occasional one: `escalate_to_slowbrain()` publishes
    `escalate.requested` synchronously and returns, but `dispatch.run_listener` registers the SessionRecord that
    `has_live_worker` checks for ASYNCHRONOUSLY, on its own task — this function runs moments later, in the SAME
    synchronous turn that just published, before the event loop has given the listener a scheduler turn to react
    at all. Without this guard `has_live_worker` is reliably still False and the flow closes seconds before the
    worker it just spawned even starts (confirmed sub-ms apart on a real trace). Bounded, not indefinite: whatever
    `run_listener` decides — spawn (its own `_run_session` finally block closes it for real), reject-while-halted,
    or dedup-inject into a live session — always emits its own explicit close (`dispatch._close_escalated_flow`
    for the latter two), so this never leaves a flow stuck open."""
    if not tid:
        return False
    if acc_trace_id == tid:
        return False           # the V2-096 accumulator still expects a continuation on THIS trace
    if tid in confirm_trace_ids:
        return False           # a question asked on this trace is still waiting for the operator's answer
    if has_live_worker:
        return False           # a worker spawned on this trace is still running — IT owns the close
    if just_escalated:
        return False           # escalate.requested just published on THIS trace — see docstring above
    return True


# Turn TEXT can finish generating well before its own TTS finishes narrating it — closing the flow right then
# made the master board's column vanish while the agent was still audibly speaking (operator report, 2026-08-16:
# "le he hecho una pregunta... el turno ha desaparecido... la gente todavía me está contestando"). `_run()`'s
# success branch used to close immediately; now, if the bot is still speaking, it only QUEUES the close here and
# `agent.py`'s `on_state_change` drains the queue on the next speaking→idle transition (real audio playout done,
# see `agent_activity.py`'s post-playout state update — not the LLM stream returning, which fires from a sibling
# task and can't see it). Trace ids are captured HERE, inside this stream's OWN task, the only place
# `voice.trace.current()` is guaranteed to be THIS turn's — a later cross-task read could already see a newer
# turn's trace (LiveKit's `preemptive_generation`). The close itself uses `trace.scope(tid)` to stamp the event
# explicitly rather than relying on whatever trace happens to be ambient when the queue drains.
_PENDING_FLOW_CLOSES: dict[str, "NucleoLLM"] = {}


def drain_pending_flow_closes() -> None:
    """Nothing is speaking right now — safe to resolve every flow queued by `_maybe_close_flow` while its own
    TTS was still in flight. Re-checks each one's close conditions fresh (a confirm/worker could have started
    since it was queued), it doesn't just trust the snapshot taken at queue time."""
    if not _PENDING_FLOW_CLOSES:
        return
    pending = list(_PENDING_FLOW_CLOSES.items())
    _PENDING_FLOW_CLOSES.clear()
    for tid, brain in pending:
        _close_flow_now(tid, brain)


def _close_flow_now(tid: str, brain: "NucleoLLM") -> None:
    try:
        from nucleo import dispatch as _disp_close
        confirm_trace_ids = {v.get("trace_id") for v in _wconfirm.pending().values()}
        _just_esc = (getattr(brain, "_escalated_trace_id", "") == tid)
        if not _flow_should_close(tid, getattr(brain, "_acc_trace_id", ""), confirm_trace_ids,
                                   _disp_close.has_live_trace(tid),
                                   just_escalated=_just_esc):
            return
        from voice import trace as _trace
        from voice.observer import emit as _emit_close
        # This turn was ABOUT a task already running → fuse the two flows instead of closing a second column
        # (V2-123). The absorbed trace does NOT emit its own end: a close counts for the folded row, so closing
        # here would mark the still-working titular as finished and drop it off the board. The worker owns it.
        _target = _merge_target(tid, _disp_close.live_traces(),
                                getattr(brain, "_turn_tools", ()), just_escalated=_just_esc)
        if _target:
            _trace.merge(_target, tid)
            return
        with _trace.scope(tid):
            _emit_close("flow", "end", role="system", extra={"ok": True, "reason": "turn_complete"})
    except Exception:
        pass


def _maybe_close_flow(brain: "NucleoLLM") -> None:
    """Called once a turn finishes CLEANLY (V2-090 addenda, 2026-08-15) — never on a barge-in cancellation
    (`_run`'s `except asyncio.CancelledError` branch skips this on purpose: whether a cancelled turn's trace gets
    continued by the next fragment or abandoned isn't knowable yet at cancellation time). Queues instead of
    closing outright when the bot is still speaking (see module comment above `_PENDING_FLOW_CLOSES`)."""
    try:
        from voice import trace as _trace
        tid = _trace.current()
        if not tid:
            return
        from voice import proactive as _proactive
        if _proactive.bot_speaking():
            _PENDING_FLOW_CLOSES[tid] = brain
            return
        _close_flow_now(tid, brain)
    except Exception:
        pass


def _release_acc_trace_if_fresh(brain: "NucleoLLM") -> None:
    """Real bug diagnosed live (2026-08-16): "cierra todos los widgets" turns sat "EN CURSO" in the master
    forever despite doing their job — closing the widgets — correctly. `_begin_or_adopt_trace()` sets
    `brain._acc_trace_id` for EVERY fresh (non-continuation) turn, on the assumption that the accumulator's
    `offer()` call further down `_run_inner` will clear it once the utterance resolves as complete. Three
    early-exit branches (hard interrupt, echo suppression, the not-directed/ambient gate) `return` BEFORE ever
    reaching `offer()` — their trace never gets released, and `_flow_should_close()`'s "a chain still expects a
    continuation on THIS trace" guard (there to protect a REAL pending fragment chain) ends up blocking that
    exact flow from EVER closing, since nothing later ever revisits the decision.

    Only safe to clear when the accumulator has nothing buffered: if it does, `_acc_trace_id` may belong to a
    genuine unresolved chain this turn merely ADOPTED (`_begin_or_adopt_trace`'s other branch, e.g. a "para"
    said mid-fragment) — clearing it there would end that unrelated chain's protection early, not just this
    turn's own bookkeeping."""
    if not getattr(brain, "_acc", None) or not brain._acc.pending():
        brain._acc_trace_id = ""
