"""What a turn owes when it stops talking — ONE seam for both channels (V2-661, extracted).

Three repairs that had grown side by side inside `voice/engine/llm/providers/nucleo.py` and, mirrored, inside
`nucleo/flash/probe.py`:

* **the errand HARNESS** (V2-660): every card a turn SHOWED is an end state it implied (`note_shown`) — the prompt
  carries an unmet one as a fact; reading the reply for a CLAIM of delivery and speaking a follow-up went in V2-851 F5;
* **the oversized `widget_data`** (V2-658): a widget write cut by the token cap is not a void, it is content
  that does not fit a voice turn — a WORKER's delivery, never «¿me lo repites?»;
* **the ASIDE** (V2-657): a `[[aparte]]` turn is sanctioned silence, so the window refresh its admission wrote
  is retracted and the fact lands on the timeline.

They belong together because they answer the same question — *what does this turn still owe?* — and because
the two channels must never drift apart on it (the parallel-implementation rule, V2-252/V2-555). The provider
and the probe now call the SAME decision and only differ in how they carry it out: the voice channel speaks the
follow-up (its sentence has already streamed), the probe synthesizes the tool call.

The two language-dependent SENTENCES this used to compose (the honest follow-up, the holding line) live in
`reminder_guards`: this seam may not reach into the motor's internals (the V2-569 ratchet) and that module
already owns the canned lines of a turn with nothing to say.

Nothing here touches the network, the model or the canvas: it reads what the turn already produced and returns
a decision. Fail-soft by construction — a repair that raises must never cost the operator his turn.
"""
from __future__ import annotations

from loguru import logger

def note_shown(shown_ids, words: str, *, trace: str = "") -> None:
    """Every card this turn showed becomes an open GOAL of the harness (content in it)."""
    try:
        from nucleo.circuit import harness
        for wid in list(shown_ids or []):
            if wid:
                harness.note_goal(harness.KIND_WIDGET_CONTENT, str(wid), words, trace=trace)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"harness goals skipped: {e}")


def current_trace() -> str:
    """The flow this turn belongs to, or "" — a goal without its trace is still a goal."""
    try:
        from voice import trace
        return trace.current() or ""
    except Exception:  # noqa: BLE001
        return ""


def oversized(turn_text: str, metrics) -> dict | None:
    """A `widget_data` write the token cap cut is a WORKER's delivery (V2-658), or None. `{request, surface, head}`.

    A fact of the turn's own call (its metrics), read after the stream, never a model call and never a line: the
    turn's commission carries it. Its sibling — a reply that CLAIMED delivery over an empty sheet, answered with a
    follow-up line and an escalation (`rescue`) — went in V2-851 F5 with every line spoken after the reply."""
    head = None
    if metrics is not None:
        try:
            from nucleo.llm.fast_client import oversized_widget_write
            head = oversized_widget_write(metrics)
        except Exception:  # noqa: BLE001
            head = None
    if not head:
        return None
    return {"request": (turn_text + " — [el turno de voz intentó escribir este contenido en un widget y NO "
                        "CABE en un turno: complétalo y entrégalo al widget documento con `append` por "
                        "secciones. Lo que empezaba a escribir: " + head + "…]"),
            "surface": "documento", "head": head}


def turn_handled(*, typed: bool, widget=False, data=False, worker=False, style=False, deduped=False,
                 aside=False, escalated=False, searched=False, music=False, video=False, images=False,
                 confirm=False) -> bool:
    """Did this turn DO something, so a mute reply is legitimate rather than a void? (extracted V2-661)

    Live bug (search-buy-used-car, 2026-08-17): after several check-ins with a worker running, a pure-chat turn
    («¿pudiste relanzarla?») came back genuinely empty; every earlier backstop is gated on ITS own action, so
    nobody covered this case — the operator got no answer and the NEXT turn, seeing that hole in the window,
    ECHOED his own question word for word. The generic backstop is the last resort for exactly that.

    V2-634 (session b828c901): with the V2-633 silent-orders gate on, a turn that DID act (play_video → load)
    ended with an empty reply and fell into the backstop — four apologies («se me ha ido») over turns that had
    executed perfectly, reading as not-understanding. The stuck apology is for turns that produced NOTHING.

    V2-646 (22:30:39): he TYPED «puedes ponermela en youtube o de alguna forma?», the model spent its 51 tokens
    on a `play_video` the canvas-license guard vetoed as context-bleed, `deduped` marked the turn handled, and
    the backstop stayed quiet — a written question answered with nothing. The V2-633/634 exemptions exist for
    AMBIENT speech dragged in from the room, where silence is the right answer; a sentence somebody sat down and
    WROTE is never that. So on a TYPED turn a vetoed/deduped action does not count as handled — and neither does
    an ASIDE (V2-657), which is deliberate silence towards somebody else in the room.
    """
    return bool(widget or data or worker or style
                or (deduped and not typed) or (aside and not typed) or (video and not typed)
                or escalated or searched or music or images or confirm)


def note_aside(text: str, *, attention, emit) -> None:
    """A `[[aparte]]` turn: retract the window refresh its admission wrote — so table talk cannot keep the
    conversation alive forever (the 2026-09-10 dinner spiral) — and put the sanctioned silence on the timeline,
    because a silence nobody can see reads as a fault."""
    retracted = False
    try:
        retracted = attention.retract_last_directed()
    except Exception:  # noqa: BLE001
        pass
    emit("ambient", "🙊 aparte — dirigida a otra persona (el modelo la dejó pasar)", text=text[:120],
         role="user", extra={"reason": "aside", "retracted": retracted,
                             "window_s": attention.window_s(), "window_open": attention.window_open()})
