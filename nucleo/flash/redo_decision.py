"""nucleo/flash/redo_decision.py — a complaint about what we just did is an order to do it RIGHT.

THE DEFECT THIS EXISTS FOR (live session fce3eff3, 2026-09-22). He asked for a list of Apollo videos.
The STT heard «Apolón», the search ran on «vídeos del Apolo», and the player filled with videos from
channels called Apolo — nothing to do with the mission. He corrected it twice, and BOTH corrections
were correct at the model and killed by a guard:

    +149.4 s  «He dicho, Apollo once.»
              → the model emitted the search, query="Apollo 11"
              → 🛡️ play_video ignorado (context-bleed)
              → ⚠️ promesa sin acción — it SAID «Voy con Apollo 11» and did nothing

    +164.9 s  «Yo sigo viendo en pantalla los mismos vídeos de la primera vez»
              → the model emitted the search, query="Apollo 11"
              → 🛡️ play_video ignorado (context-bleed)
              → ⚠️ promesa sin acción — «te los refresco» and did nothing

It landed on the third try, when he spelled it out with a media noun in the sentence. His question
afterwards was «¿Cómo es posible que haya costado tanto llegar hasta aquí?», and the honest answer is
that it had been right since the first correction.

## WHY EVERY EXISTING READER SAID NO, CORRECTLY

`canvas_license.video_license` asks two things and both were right to refuse:

  · the grammar (`_MEDIA_REQ_RE`) — «He dicho, Apollo once.» carries no media verb and no media noun.
    True. It is a correction, and a correction borrows its subject from the thing it corrects.
  · the turn's verdict — `screen_action = none` at 0.92, `request_type = comment` at 0.99. Also true:
    read in isolation, that sentence asks for nothing.

Every licence in this engine is computed from THIS turn's words plus a verdict about THIS turn in
isolation. Nothing anywhere asks the question the situation actually poses: **is he telling me I got
the last one wrong?** The engine even DETECTS the complaint — `🗣️ queja sobre lo ya hecho` fired five
times in that session — and uses it only to SUPPRESS, never to repair.

## THE RULE

`corrects_last` asks, with what we actually just did in front of it: is this turn correcting that, a
new request, or about something else? A confident `corrects_last` GRANTS the licence of the op it
corrects — nothing more. It cannot start work of its own, it cannot reach a generator, and it cannot
license an action the operator's turn does not already carry a tool call for: the model had ALREADY
emitted the right call in both measured cases, and all this does is stop a guard from eating it.

That asymmetry is the same one `build_decision` uses and for the same reason: this verdict can only
ever let through work the turn was already doing, which is the cheap direction.

## PLACEMENT — POST-MODEL, SO IT IS FREE

Read after the model has spoken, like every other brief verdict (V2-726): the brief lands at ~785 ms
and this is consulted 2-4 s later, inside the tool gate. Unlike `continuation`, nothing here has to be
decided before the turn starts, so nothing here is paid for in latency.
"""
from __future__ import annotations

REDO_KEY = "corrects_last"

REDO_INSTRUCTIONS = (
    "We just did something for the operator, described below. Is what he is saying now telling us that "
    "what we did is WRONG or not what he asked for — so that the right response is to do that same thing "
    "again, properly? Answer 'corrects_last' when he is correcting, rejecting or repeating the request we "
    "just acted on, including when he only supplies the detail we got wrong. Answer 'new_request' when he "
    "is asking for something else. Answer 'unrelated' when he is not talking about what we did at all.")

REDO_CHOICE = {
    "corrects_last": "he is telling us the thing we just did is wrong, and wants it done right",
    "new_request": "he is asking for something different",
    "unrelated": "he is not talking about what we just did",
}

#: Same gate as every other verdict reader. A shrug keeps today's path.
MIN_CONFIDENCE = 0.5

#: How far back a mutation is still «what we just did» for this question. Much shorter than
#: `done_ops.WINDOW_S` (30 min), which answers a different question — whether a destructive op already
#: ran. A correction follows its target within a turn or two; measured in that session, both were inside
#: 20 s. Beyond this he is starting something new, and reading it as a correction would re-run an old op.
WINDOW_S = 120.0


def last_op(within_s: float = WINDOW_S) -> dict | None:
    """The most recent mutation that actually ran, or None. Never raises."""
    try:
        from nucleo import done_ops
        rows = done_ops.recent(within_s=within_s, limit=1)
        return rows[-1] if rows else None
    except Exception:  # noqa: BLE001
        return None


def _describe(op: dict) -> str:
    wid, action = str(op.get("wid") or ""), str(op.get("action") or "")
    payload = op.get("payload") or {}
    detail = ", ".join(f"{k}={v}" for k, v in list(payload.items())[:3] if str(v).strip())
    return f"{wid}:{action}" + (f" ({detail})" if detail else "")


def question(within_s: float = WINDOW_S) -> dict | None:
    """The question, or None when there is nothing we just did for it to be about.

    Returning None is what keeps this from being asked on a cold canvas: with no recent op the answer
    could only ever be `unrelated`, and a question whose answer is known is a question not worth its
    place in the brief.
    """
    op = last_op(within_s)
    if not op:
        return None
    return {"instructions": f"{REDO_INSTRUCTIONS} [What we just did: {_describe(op)}]",
            "criteria": dict(REDO_CHOICE)}


def corrects(brief, widget: str = "") -> bool:
    """True when this turn is a confident correction of an op on `widget` (or on anything, if "").

    The widget check is what stops a complaint about the agenda from licensing a video load: a
    correction grants the licence of the op it corrects, and only that one.
    """
    if not brief:
        return False
    try:
        from nucleo.flash import turn_brief as _tb
        # `read` applies the confidence gate itself and returns the fallback below it, so reaching this
        # value at all means it was READY and SURE. `info` is the attribution trail, not a second gate —
        # treating it as one would make an unsure verdict and a used one indistinguishable here.
        choice, _info = _tb.read(brief, REDO_KEY, "")
        if str(choice or "") != "corrects_last":
            return False
        if not widget:
            return True
        op = last_op()
        return bool(op) and str(op.get("wid") or "").strip().lower() == widget.strip().lower()
    except Exception:  # noqa: BLE001
        return False
