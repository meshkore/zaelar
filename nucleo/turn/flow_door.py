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
        from nucleo.acts import surface_owner as _own
        if _own.turn_was_discarded(t):
            _emit("🧵 a discarded turn starts nothing — its chain carries the request", req, {"as": "discarded"})
            return False
        from nucleo.turn import brief as _tb, flow_of as _flow
        r = _flow.for_request(req, _tb.of_this_turn())
        ctx["routed"] = f"{r['as']}:{r.get('flow', '')}"
        how = r["as"]
        if how in (_flow.NEW, "replace"):
            return True
        if how == _flow.CONVERSATION:
            _emit("🧵 conversation — no errand to commission", req, r)
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
        _emit("🧵 the turn's stop covers this errand — nothing new is started", req, r)
        return False
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
