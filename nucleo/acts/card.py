"""The card door's licence (refactor2710-05 T-02): may THIS turn's request run this data-op on a card?

The vetoes over a `widget_data` call are ONE ladder, declared once (`_LADDER`), read by `licence(request, ...)` at
the moments the door knows enough to judge; the caller only does what the answer says:

  · `CALL` — the model's call, before anything is resolved: a pure «show me X» runs no invented mutation; a short
    close order closes the card; a `close` data-op needs his close (or the verdict's).
  · `DECLARED` — once the action is a declared one (an invented name repaired): a question writes nothing.
  · `GATE` — every path that reaches the gate (the call, a tag, a repair): a close verdict closes the card instead of
    running its `close` view; the tail of a sentence moves nothing.
  · `LEAVES` — an act that leaves with no question, which the verdict does not dispute: dropped (asked instead) when
    the verdict puts the turn on ANOTHER card.
  · `FAST` — an op about to run with no question: a repeat of the last op his words never order is drag
    (context-bleed); the same refused op re-sent identically is the model re-reading its failure.
  · `LOAD` — a load that replaces what plays runs only on his order (verdict, named content, correction, our offer).

A clause answers `SHOW` / `CLOSE` / `DROP` (the call does not run) or nothing; `RUN` is the ladder's end. Each answer
carries its event. `request` is `{"brief", "text"}`; his half is taken here, once.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from loguru import logger

from nucleo.acts.outcome import Outcome
from nucleo.circuit import verdict as V

CALL, DECLARED, GATE, LEAVES, FAST, LOAD = "call", "declared", "gate", "leaves", "fast", "load"
RUN, SHOW, CLOSE, DROP = "run", "show", "close", "drop"


@dataclass(frozen=True)
class Licence:
    verdict: str = RUN
    clause: str = ""
    label: str = ""
    text: str = ""
    extra: dict = field(default_factory=dict)
    card: str = ""          # the card a SHOW/CLOSE acts on

    def outcome(self) -> Outcome:   # a vetoed call fired nothing; a SHOW/CLOSE moved the canvas instead
        if self.verdict == RUN:
            return Outcome(False, V.STARTED.name)
        return Outcome(self.verdict != DROP, V.SKIPPED.name, data={"clause": self.clause, "card": self.card})


def _his(request) -> str:
    from voice import brain_notes as _bn
    return _bn.operator_half(str((request or {}).get("text") or ""))


def _ex(wid, action, payload) -> dict:  # what a dropped op's event carries
    return {"id": wid, "action": action, "payload": payload or {}}


# ── CALL · DECLARED ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _pure_show(r, wid, action, payload, **_k):
    """A pure show order runs no invented mutation; a `view` runs beside it (V2-545), the verdict licenses (V2-753)."""
    from nucleo.flash import direct_action as _da, router as _router
    from widgets import runtime
    text = str((r or {}).get("text") or "")
    if runtime.get(wid) is None or not _router.is_pure_show_request(text):
        return None
    if (_router.show_request_blocks_data_action(text, wid, action, payload)
            and not _da.endorses((r or {}).get("brief"), wid, action)):
        return Licence(SHOW, "pure-show", "🪟 'abrir/mostrar' puro → show (no data-op inventada)",
                       f"{wid} (descartada {action})", _ex(wid, action, payload), wid)
    return None


def _short_close(r, wid, action, payload, **_k):
    """A short clear close order («Vale, ciérralo») closes the card, whatever op the model sent (V2-713 R3 / V2-781)."""
    from nucleo.flash import card_close as _cc
    from widgets import runtime
    if runtime.get(wid) is not None and _cc.data_close(wid, action, str((r or {}).get("text") or ""),
                                                       brief=(r or {}).get("brief")):
        return Licence(CLOSE, "short-close", "🙈 orden corta de CERRAR → close (no data-op)", f"{wid} (era {action})",
                       {}, wid)
    return None


def _unlicensed_close(r, wid, action, payload, *, emit=None, **_k):
    """V2-635: the `close` data-op EMPTIES the card; with no close of his (or the verdict's) it is drag (logs its own)."""
    if action != "close":
        return None
    from nucleo.flash import close_guards as _cg
    if _cg.dataop_close_licensed(str((r or {}).get("text") or ""), wid, brief=(r or {}).get("brief"), emit=emit):
        return None
    return Licence(DROP, "unlicensed-close")


def question_keeps_unwritten(wid: str, action: str, operator_text: str, brief) -> bool:
    """A WRITE on his QUESTION («?») while the verdict read, surely, no action on screen. Never raises (CRIT-K2)."""
    try:
        if "?" not in (operator_text or "") and "¿" not in (operator_text or ""):
            return False
        from widgets import effects as _fx
        if not _fx.carries(wid, action, _fx.DATA_WRITE):
            return False
        from nucleo.turn import brief as _tb
        choice, info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=0.8)
        return bool((info or {}).get("used")) and str(choice or "") == "none"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"acts.card: a question unreadable ({e}) — the call runs")
        return False


def _a_question(r, wid, action, payload, **_k):
    """A write is the costly reading of a question (demo pass 93 R2): not run; the card is shown."""
    if question_keeps_unwritten(wid, action, _his(r), (r or {}).get("brief")):
        return Licence(SHOW, "a-question", "❓ una pregunta no escribe — el veredicto no pedía acción",
                       f"{wid}:{action}", {"cat": "flash", "id": wid, "action": action}, wid)
    return None


# ── GATE ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _close_is_the_card(r, wid, action, payload, **_k):
    """E5 (demo passes 36/42): «close my mail» ran the card's `close` VIEW over a sure close verdict."""
    from nucleo.flash import direct_action as _da, show_target as _st
    if _da.close_op_is_the_card((r or {}).get("brief"), action):
        return Licence(CLOSE, "close-is-the-card", "🔁 data-op «close» sobre un cierre seguro — cierra la tarjeta",
                       wid, {"cat": "flash", "widget": wid, "action": "close"}, _st.close_target(wid))
    return None


def _a_fragment(r, wid, action, payload, *, last_reply="", **_k):
    """V2-757 — a sentence's tail is not an order (why: `direct_action.a_fragment_moves_nothing`)."""
    from nucleo.flash import direct_action as _da
    said = _his(r)
    why = _da.a_fragment_moves_nothing(said, brief=(r or {}).get("brief"), last_reply=last_reply)
    if why:
        return Licence(DROP, "a-fragment", "🧩 trozo de frase — no mueve nada en pantalla",
                       f"{said.strip()[:80]} → {wid}:{action}", {"cat": "flash", "why": why, "id": wid, "action": action})
    return None


# ── LEAVES · FAST ─────────────────────────────────────────────────────────────────────────────────────────────────────

def _leaves_for_another_card(r, wid, action, payload, **_k):
    """An act that leaves while the verdict puts the turn on ANOTHER card is dropped, not offered (demo pass 45)."""
    from nucleo.flash import direct_action as _da
    if not _da.verdict_elsewhere((r or {}).get("brief"), wid):
        return None
    try:
        from voice import brain_notes as _bn
        _bn.push(f"[SISTEMA] La acción «{action}» sobre «{wid}» NO se ejecutó: el operador no la pidió (su orden era "
                 f"otra). No digas que se ha enviado ni lo ofrezcas; si él te lo pide explícitamente, llama entonces a "
                 f"«{action}».")
    except Exception as e:  # noqa: BLE001 — the drop stands without the note
        logger.debug(f"acts.card: drop note not pushed ({e})")
    return Licence(DROP, "leaves-for-another-card", "🛑 acto que sale fuera sin respaldo del veredicto — no se ejecuta",
                   f"{wid}:{action} · veredicto en otra tarjeta", {"cat": "flash", "id": wid, "model": action})


def _context_bleed(r, wid, action, payload, *, last_dataop=None, **_k):
    """An IDENTICAL mutation to the last one (<120 s) his turn never mentions is drag, unless he orders it again or
    redoes it; a VIEW-op never is (`data_ops.is_context_bleed`, V2-038/650/791)."""
    from nucleo.flash import data_ops as _do
    if _do.is_context_bleed(last_dataop, wid, action, payload, _his(r), brief=(r or {}).get("brief")):
        return Licence(DROP, "context-bleed", "🛡️ data-op del turno anterior re-emitida — ignorada (context-bleed)",
                       f"{wid}:{action}", _ex(wid, action, payload))
    return None


def _refused_again(r, wid, action, payload, **_k):
    """V2-773 — the SAME refused op with the SAME payload is the model re-reading the failure; a corrected one runs."""
    from nucleo.flash import data_ops as _do
    if _do.is_identical_retry_of_refused(wid, action, payload):
        return Licence(DROP, "refused-again", "🛡️ reintento idéntico de una op rechazada — ignorado", f"{wid}:{action}",
                       _ex(wid, action, payload))
    return None


#: How sure a verdict must be to CONTRADICT the model's call (V2-825 F4): a veto is the irreversible side.
VETO_SURE = 0.85


def vetoes(brief, wid: str, model_action: str, verdict_action: str) -> str:
    """The event a SURE verdict vetoes the model's call on the same card with, or "": a question over a WRITE (full19
    C2) and a lens over a state change (full52 V5). Never raises."""
    try:
        from nucleo.flash import data_ops as _do, direct_action as _da
        from widgets import effects as _fx
        if not _da._action_sure(brief, floor=VETO_SURE):
            return ""
        if _fx.carries(wid, verdict_action, _fx.OUTPUT_ANSWER) and _fx.carries(wid, model_action, _fx.DATA_WRITE):
            return "❓ la pregunta gana a la escritura — corre el veredicto"
        if _do.is_view_op(wid, verdict_action) and not _do.is_view_op(wid, model_action):
            return "👁 la vista segura gana a un cambio de estado — corre el veredicto"
    except Exception as e:  # noqa: BLE001
        logger.debug(f"acts.card: veto unreadable ({e}) — the model's call runs")
    return ""


def _a_load_he_did_not_order(r, wid, action, payload, *, last_reply="", query="", **_k):
    """`play_video` runs on his order, read without words (CRIT-K5b); fail-closed: none, dropped and said."""
    from nucleo.flash import canvas_license as _lic, prior_line as _pl, redo_decision as _redo
    brief, said = (r or {}).get("brief"), _his(r)
    if (_lic.verdict_grants(brief, wid) or (query and _lic.names_what_to_play(query, said))
            or _redo.corrects(brief, wid)
            or (_pl.answers_our_question(brief, last_reply) and _lic.offer_of_media(last_reply))):
        return None
    return Licence(DROP, "load", "🛡️ play_video ignorado — el turno no pide ningún vídeo (context-bleed)",
                   said[:120], {"cat": "flash", "kind_diag": "video_without_order", "query": str(query)[:80]})


#: The ladder, in the order it is read at each moment. Declared once; a new veto is a clause here, never an `if`.
_LADDER = {LOAD: (_a_load_he_did_not_order,), CALL: (_pure_show, _short_close, _unlicensed_close), DECLARED: (_a_question,),
           GATE: (_close_is_the_card, _a_fragment), LEAVES: (_leaves_for_another_card,),
           FAST: (_context_bleed, _refused_again)}


def licence(request, wid: str, action: str, payload=None, *, at: str, **known) -> Licence:
    """The first clause of `at` that vetoes this call, or `RUN`. `known` is what that moment knows (`last_dataop`,
    `last_reply`, `emit`). Never raises: an unreadable clause does not veto (CRIT-K2)."""
    for clause in _LADDER[at]:
        try:
            got = clause(request, wid, action, payload, **known)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"acts.card: clause {clause.__name__} unreadable ({e}) — it does not veto")
            continue
        if got is not None:
            return got
    return Licence()


def logged(lic: Licence, emit) -> Licence:
    """Emit the licence's own event (a clause that logged its reason itself carries no label)."""
    if lic.label:
        emit("brain", lic.label, text=lic.text, role="system", extra=lic.extra)
    return lic
