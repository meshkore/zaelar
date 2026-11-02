"""What the escalation portal DOES with a turn's route (V2-844 F2) — the consequence half of `flow_of.route`.

Every door that starts work reaches `errand.escalate_to_slowbrain`, so the portal is where the route is obeyed: a
request that is conversation commissions nothing; one that belongs to a live errand reaches it (the one relay door);
one an errand parked on his yes covers is absorbed and the question is asked again; one a stop verdict covers starts
nothing; one that continues an ended or starting flow goes on in ITS sheet; a turn discarded unanswered hands its
launch to its chain and starts nothing itself. Only `new` and `replace` open an errand of their own.

A request that already carries its errand (a relay, a retry, a reopen, a confirmed relaunch, a first-rung hand-on, a
caller that routed it) is not routed again. Outside a turn (no trace) nothing is routed: the dispatcher decides, as it
always did. The dispatcher's dedup stays behind this door as a backstop that folds and WARNS.
"""
from __future__ import annotations

from loguru import logger

#: Context keys that say the request already has its errand — or its route — so the portal must not route it again.
_CARRIES = ("task_uid", "born_uid", "confirmed", "routed", "replaces", "not_mine_of")


def _emit(label: str, req: str, r: dict) -> None:
    try:
        from voice.observer import emit
        emit("flow", label, role="system", text=req[:160],
             extra={"cat": "flash", "as": r.get("as"), "flow": r.get("flow", ""), "sheet": r.get("sheet", ""),
                    "v": "V2-844"})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"flow_door: not recorded — {e!r}")


def fold_note(words: str) -> str:
    """His words as they reach an errand the route folded them into, with the way back if they are not its business
    (V2-784 F5): the worker hands them back and they become an errand of their own."""
    return (f"{words}\n\n(If this is NOT about your task, hand it back instead of acting on it: write "
            "{\"words\": \"<his words>\"} to a relative file and run 'python -m nucleo.cli.bridge act not_mine @<file>.json'.)")


def ask_again(question: str) -> None:
    """His words joined an errand parked on his yes: the brain asks that question again (the dispatcher's backstop says
    the same through here)."""
    from voice import brain_notes
    brain_notes.push("[SISTEMA] Eso es la MISMA tarea que está aparcada esperando su respuesta"
                     + (f": «{question[:160]}»" if question else "")
                     + ". No has abierto nada nuevo. Repítele la pregunta en una frase corta y espera su sí o su no.")


def at_the_portal(req: str, ctx: dict) -> bool:
    """Route `req` at the portal. True: the portal goes on and opens the errand (`ctx` may now name the flow's sheet);
    False: the route took it (joined, absorbed, stopped, conversation, discarded). Never raises: unreadable → True."""
    try:
        from voice import trace as _trace
        t = _trace.current()
        if not t or any(ctx.get(k) for k in _CARRIES) or ctx.get("kind") == "dev":
            return True
        from nucleo.turn import turn_marks
        if turn_marks.was_discarded(t):
            _emit("🧵 a discarded turn starts nothing — its chain carries the request", req, {"as": "discarded"})
            return False
        from nucleo.turn import brief as _tb, flow_of as _flow
        r = _flow.for_request(req, _tb.of_this_turn(), part=ctx.get("part") is not None)
        ctx["routed"] = f"{r['as']}:{r.get('flow', '')}"
        how = r["as"]
        if how in (_flow.NEW, "replace"):
            return True
        if how == _flow.CONVERSATION:
            _emit("🧵 conversation — no errand to commission", req, r)
            from voice import brain_notes        # the model reads it: no silent 0 behind a promise
            brain_notes.push("[SISTEMA] Eso no era un encargo nuevo ni de ninguna tarea abierta: no has abierto nada. "
                             "Si le prometiste ponerte con algo, díselo tal cual en una frase.")
            return False
        if how in (_flow.REOPEN, _flow.JOIN):
            if r.get("sheet"):
                ctx["sheet"] = r["sheet"]
            return True
        if how == _flow.ABSORB:
            from nucleo.dispatch import confirm as _dc
            question = _dc.absorb_refinement(str(r["flow"]), req)
            ask_again(question)
            _emit("🧵 the request joins the errand parked on his yes", req, r)
            return False
        if how in (_flow.INJECT, "steer"):
            from nucleo import dispatch as _d
            _d.relay_his_words(str(r["flow"]), fold_note(req))
            _emit("🧵 the request reaches the live errand it belongs to", req, r)
            return False
        if how == "stop":
            _emit("🧵 the turn's stop covers this errand — nothing new is started", req, r)
            return False
        _emit("🧵 a route this portal does not know — the errand opens", req, r)
        return True                      # fail-open: an outcome nobody taught it never swallows an errand
    except Exception as e:  # noqa: BLE001 — a route that cannot be read never blocks an errand
        logger.warning(f"flow_door: route unreadable at the portal, the errand opens — {type(e).__name__}: {e}")
        return True


def backstop(target: str, ctx: dict | None, how: str, *, orphan: str = "") -> bool:
    """The dispatcher folded an escalation into `target` (`how`: live · parked · continuity) — the backstop behind the
    door. It FOLDS either way; it WARNS when the door did not route the request there (`ctx["routed"]`, V2-844 F2):
    that is the door missing, with its evidence. True when it warned. Never raises."""
    routed = str((ctx or {}).get("routed") or "")
    if routed.split(":", 1)[-1].removeprefix("esc:") == str(target).removeprefix("esc:") and routed.split(":", 1)[0] != "new":
        return False
    try:
        from voice.observer import emit
        emit("alert", "🧵 fusión tardía: la petición llegó al despachador sin pasar por su flujo", role="system",
             text=f"→ {target}" + (f" · hoja huérfana {orphan} cerrada" if orphan else ""),
             extra={"cat": "flash", "flow": target, "orphan_sheet": orphan, "how": how, "routed": routed, "v": "V2-844"})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"flow_of: the backstop's warning into {target} was lost: {e}")
    return True


async def join(text: str) -> dict:
    """The listing door's use of the route: `{}` for a new flow; `{flow, sheet}` to re-run into an open flow's sheet
    (its errand's, when it has none yet); `{flow, sheet, absorbed, question}` when an errand parked on his yes took the
    words; `{flow, sheet, injected: True}` when a live worker took the request (or the turn's stop covers it). The
    turn's route, begun beside its model call, is reused when it is about these words. Never raises."""
    from nucleo.acts.errand import whole_request
    from nucleo.turn import flow_of as _f
    from nucleo.turn.errands_of_a_turn import same_errand
    words = whole_request(text)
    r = await _f.settled()
    if r is None or not (r.get("text") == words or same_errand(words, r.get("text") or "")):
        try:
            from voice.observer import emit
        except Exception:  # noqa: BLE001 — a headless caller has no timeline
            emit = None
        from nucleo.turn import brief as _tb
        r = await _f.route(text, brief=_tb.of_this_turn(), emit=emit)
    how, fid = r.get("as"), str(r.get("flow") or "")
    if how == _f.LIST:     # its part by identity, never by likeness (the whole sentence is like every part)
        part = next((p for p in r["parts"] if _f._flat(p["words"]) == _f._flat(words)), None)
        how, fid = (part["as"], part["flow"]) if part else (_f.NEW, "")
        r = part or r
    sheet = str(r.get("sheet") or "")
    if how == "stop":     # the turn's stop covers it: nothing relaunched, nothing pretended
        return {"flow": fid, "sheet": sheet, "stopped": True}
    if how == _f.ABSORB:
        # V2-843 — an errand parked on his yes takes the words and is NOT relaunched: the same consequence as the
        # dispatcher's parked branch (`absorb_refinement`), decided here, before anything is opened.
        from nucleo.dispatch import confirm as _dc
        return {"flow": fid, "sheet": sheet, "absorbed": True, "question": _dc.absorb_refinement(fid, str(text))}
    if how in (_f.INJECT, "steer"):
        try:
            from nucleo import dispatch as _d
            if _d.his_words_may_reach_an_errand() and await _d.inject(fid, fold_note(str(text))):
                return {"flow": fid, "sheet": sheet, "injected": True}
        except Exception as e:  # noqa: BLE001 — a failed inject falls back to its sheet, never to a second one
            logger.warning(f"flow_of: inject into {fid} failed — {type(e).__name__}: {e}")
    # V2-843 S1/S2 — a covered request never mints a box: a flow with no sheet yet lands in the one its errand's id names.
    return {"flow": fid, "sheet": sheet} if fid and sheet and how not in (_f.NEW, "replace", _f.CONVERSATION) else {}
