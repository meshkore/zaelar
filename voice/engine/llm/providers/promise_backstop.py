"""The promise-without-action backstop, and the forced escalation behind it.

Extracted from `nucleo.py`'s turn body (2026-09-01), the same way `vault_intercept.py` was: the architecture
ratchet asks for a module rather than a taller ceiling, and this block had just grown a guard.

TWO decisions live here, and they pull in opposite directions.

* **V2-049** — a reply that PROMISES a web errand and calls no tool used to leave the operator waiting on
  nothing («me pongo con ello» and then silence, six minutes, session ITV). So we escalate for it,
  deterministically.
* **V2-534** — a CONFIDENT `handle_inline` never becomes a forced worker (V2-753 below).

Since refactor2710-03 the trigger is the turn's brief (`reply.owes_an_act`: an order or an escalation, at the
brief's confidence) and no act fired — never what our reply said.

Everything it reads is the OPERATOR's words (`op_text`), never the turn text: notes are glued to the front of
a turn as CONTEXT and one of them became an errand called «Cita en Valls». See `router.operator_words`.
"""
from __future__ import annotations


from loguru import logger


def _a_refinement_of_the_errand_it_names(spoken_text: str, op_text: str, emit, brief=None) -> bool:
    """A promise that is a refinement of one of his LIVE errands goes to that errand (the probe channel runs the
    same decision, `errands_of_a_turn.promised_refinement`). True when it was sent."""
    try:
        from nucleo.turn import errands_of_a_turn as _eot
        ref = _eot.promised_refinement(op_text, spoken_text, brief)
        if not ref:
            return False
        from nucleo import dispatch as _disp_ref
        if not _disp_ref.relay_his_words(ref, _eot.words_for(op_text, spoken_text)):
            return False              # a card owns the turn: the promise is that card's (the repair acts there)
        emit("brain", "↪️ promise → refinement of the errand it names", text=op_text[:120], role="system",
             extra={"cat": "flash", "to": ref})
        return True
    except Exception as e:  # noqa: BLE001 — the backstop below still runs
        logger.warning(f"promise backstop: refinement routing failed: {type(e).__name__}: {e}")
        return False


def run(spoken_text: str, *, did_act: bool, op_text: str, prev_pending: list,
        emit, escalate, similar_pending, brief=None) -> str:
    """Fire the backstop for a turn that promised and did nothing. Best-effort: never raises into the turn.

    Returns "routed" when it sent his words somewhere that will act (a live errand, a worker, part by part) — the
    turn end then owes no «I have not done it» (V2-790, `nucleo/turn/promise_kept.py`) — else ""."""
    from nucleo.turn import his_spec_to_sheet as _spec
    _spec.carry(op_text)          # every voice turn: a spec he stated about one errand reaches its sheet
    from nucleo.turn import split_by_errand as _sbe
    if not did_act and _sbe.routed(op_text):
        return "routed"           # a sentence about several errands went part by part (node 2.643)
    if did_act:
        return ""
    if _a_refinement_of_the_errand_it_names(spoken_text, op_text, emit, brief):
        return "routed"
    # refactor2710-03 — whether an act was owed is the brief's verdict, never our words (CRIT-K1/K2).
    from nucleo.turn import reply as _reply
    owed = _reply.owes_an_act(brief)
    if not owed:
        return ""

    from nucleo.flash import router as _router
    emit("brain", "⚠️ promesa sin acción (dijo que lo haría, no disparó tool)", text=(spoken_text or op_text)[:120],
         role="system", extra={"cat": "flash", "kind_diag": "promise_no_tool", "source": "brief", "owed": owed})
    try:
        if not _router.looks_like_web_task(op_text):
            return ""
        if similar_pending(op_text, prev_pending):
            from nucleo import dispatch as _disp_bk
            if _disp_bk.relay_his_words(op_text, op_text):
                emit("brain", "↪️ promesa→inyección a worker vivo (backstop)", text=op_text[:120], role="system")
                return "routed"
            return ""
        # V2-753 — and it does not overrule the turn's own paid verdict. Live session 46dcfcb4: a guard ate
        # the model's `youtube:close`, the reply became «te lo hago ahora mismo» with nothing behind it, and
        # THIS backstop forced a `claude_code` worker that opened a headless browser for four minutes to stop
        # a video — over a brief that had answered `escalate_or_inline = handle_inline` at 1.00. The operator
        # had to say «yo no te he pedido que hagas nada… páralo inmediatamente». A promise left empty by one
        # of OUR guards is not an errand; it is a bug, and spending minutes on it makes it two. Only a
        # CONFIDENT handle_inline stops the escalation — no verdict, an unsure one or a brief still in flight
        # all keep today's path bit-for-bit, because a missed errand is still worse than a wasted question.
        from nucleo.flash import escalation_guard as _eg_bk
        if _eg_bk.judge_escalation_from_brief(brief) == "handle_inline":
            emit("brain", "🚫 promesa→escalada ANULADA por el veredicto (handle_inline)", text=op_text[:120],
                 role="system", extra={"cat": "flash", "kind_diag": "promise_inline"})
            return ""
        # THE KIND IS THE CLASSIFIER'S CALL, never this backstop's (2026-08-14, session b70a45d0). Pinned to
        # `"web"` it turned a LOCAL data-op into a browser errand: «lees lo que hay en la agenda, lo borras y
        # compruebas» opened TWO browser cards nobody asked for, was labelled «Buscando en la web…», and — the
        # real damage — became «the browser task», which is how a wrong `stop_worker` found it and killed it
        # with the operator's authorisation already given. `looks_like_web_task` stays a TRIGGER only (is there
        # a management verb?): its own docstring says it exists to reclassify a bad `authenticate_web` call,
        # and its roots demand no web destination at all.
        from nucleo import dispatch as _disp_kind
        _bk_kind = _disp_kind._classify_kind(op_text)
        escalate(op_text, context={"src": "voice", "kind": _bk_kind})
        emit("brain", f"🧭 promesa→escalada FORZADA (backstop · kind={_bk_kind})",
             text=op_text[:120], role="system", extra={"cat": "flash", "kind_task": _bk_kind})
        return "routed"
    except Exception as _e_bk:  # noqa: BLE001
        logger.warning(f"promise backstop failed: {_e_bk!r}")
    return ""
