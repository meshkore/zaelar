"""The promise-without-action backstop, and the forced escalation behind it.

Extracted from `nucleo.py`'s turn body (2026-09-01), the same way `vault_intercept.py` was: the architecture
ratchet asks for a module rather than a taller ceiling, and this block had just grown a guard.

TWO decisions live here, and they pull in opposite directions.

* **V2-049** — a reply that PROMISES a web errand and calls no tool used to leave the operator waiting on
  nothing («me pongo con ello» and then silence, six minutes, session ITV). So we escalate for it,
  deterministically.
* **V2-534** — a reply that ASKS the operator for the detail it is missing is not a broken promise. Measured
  over every firing of this gate in the operator's sessions (2026-08-17 → 2026-09-01): of ten, THREE were a
  clarifying question, and the single escalation this backstop has ever produced was one of them — «¿Los
  precios de qué, Ricardo? … y te lo miro», which opened a browser he never asked for.

Everything it reads is the OPERATOR's words (`op_text`), never the turn text: notes are glued to the front of
a turn as CONTEXT and one of them became an errand called «Cita en Valls». See `router.operator_words`.
"""
from __future__ import annotations

import re as _re
import unicodedata as _ud

from loguru import logger

# First person committing to act. Deliberately narrower than `router_guards.promises_action` (which also
# serves the show/music backstops): this one gates real spending.
_COMMITTED_RE = _re.compile(
    r"\b(me pongo con|me pongo a|ahora mismo|lo hago|lo hago ya|te lo (?:reservo|busco|"
    r"miro|preparo|hago|gestiono)|arranco|voy (?:con|a por|alla|alli|ya)|me meto en|"
    r"enseguida|me encargo|lo pongo en marcha|voy alla|entro (?:en|a) la web)\b")


def _norm(s: str) -> str:
    n = _ud.normalize("NFKD", s or "")
    return "".join(c for c in n if not _ud.combining(c)).lower()


def committed(spoken_text: str) -> bool:
    """True if the reply promises, in the first person, to go and do something. A NEGATED clause does not
    («ahora mismo NO tengo ninguna tarea corriendo» — four of the gate's ten measured firings): the rule and
    its clause arithmetic live once, in `router_guards`, and both promise gates read them."""
    from nucleo.flash.router_guards import unnegated_match
    return unnegated_match(_COMMITTED_RE, _norm(spoken_text))


def run(spoken_text: str, *, did_act: bool, op_text: str, prev_pending: list,
        emit, escalate, similar_pending) -> None:
    """Fire the backstop for a turn that promised and did nothing. Best-effort: never raises into the turn."""
    if not spoken_text or did_act or not committed(spoken_text):
        return

    from nucleo.flash import router as _router
    if _router.asks_for_missing_detail(spoken_text):
        # It asked for the datum it needs, which is the correct behaviour — and the request will escalate a
        # turn later through the window lookback (V2-132). Kept as an event so the series stays measurable.
        emit("brain", "🙋 pregunta aclaratoria (no es promesa incumplida)", text=spoken_text[:120],
             role="system", extra={"cat": "flash", "kind_diag": "asks_detail"})
        return

    emit("brain", "⚠️ promesa sin acción (dijo que lo haría, no disparó tool)", text=spoken_text[:120],
         role="system", extra={"cat": "flash", "kind_diag": "promise_no_tool"})
    try:
        if not _router.looks_like_web_task(op_text):
            return
        if similar_pending(op_text, prev_pending):
            from nucleo import dispatch as _disp_bk
            _disp_bk.inject_soon(op_text, op_text)
            emit("brain", "↪️ promesa→inyección a worker vivo (backstop)", text=op_text[:120], role="system")
            return
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
    except Exception as _e_bk:  # noqa: BLE001
        logger.warning(f"backstop promesa falló: {_e_bk}")
