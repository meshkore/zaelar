"""What a turn owes when it stops talking — ONE seam for both channels (V2-661, extracted).

Three repairs that had grown side by side inside `voice/engine/llm/providers/nucleo.py` and, mirrored, inside
`nucleo/flash/probe.py`:

* **the errand HARNESS** (V2-660): every card a turn SHOWED is an end state it implied, and a reply that CLAIMS
  delivery over a card the harness reads as EMPTY is a false claim — the honest follow-up is spoken and the
  errand escalates with the doc surface, carrying the operator's own words;
* **the oversized `widget_data`** (V2-658): a widget write cut by the token cap is not a void, it is content
  that does not fit a voice turn — a WORKER's delivery, never «¿me lo repites?»;
* **the ASIDE** (V2-657): a `[[aparte]]` turn is sanctioned silence, so the window refresh its admission wrote
  is retracted and the fact lands on the timeline.

They belong together because they answer the same question — *what does this turn still owe?* — and because
the two channels must never drift apart on it (the parallel-implementation rule, V2-252/V2-555). The provider
and the probe now call the SAME decision and only differ in how they carry it out: the voice channel speaks the
follow-up (its sentence has already streamed), the probe synthesizes the tool call.

Nothing here touches the network, the model or the canvas: it reads what the turn already produced and returns
a decision. Fail-soft by construction — a repair that raises must never cost the operator his turn.
"""
from __future__ import annotations

from loguru import logger

#: The reason a rescue fired, for the caller's observability line.
HARNESS = "harness"
OVERSIZED = "oversized"


def note_shown(shown_ids, words: str, *, trace: str = "") -> None:
    """Every card this turn showed becomes an open GOAL of the harness (content in it)."""
    try:
        from nucleo import harness
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


def follow_up_line(english: bool | None = None) -> str:
    """The honest follow-up spoken over a false claim — V2-572's shape: the missing truth, said late."""
    if english is None:
        try:
            from voice.engine.core import langs
            english = str(langs.current_code() or "").lower().startswith("en")
        except Exception:  # noqa: BLE001
            english = False
    return ("Sorry — it is not on screen yet. I am getting it ready for you." if english
            else "Perdona — todavía no está en pantalla. Te lo estoy preparando.")


async def rescue(spoken: str, *, data_done: bool, turn_text: str, metrics=None, may_escalate: bool = True):
    """What this turn owes, or None. `{request, surface, reason, goal}`.

    `data_done` guards the V2-603 fire-and-forget race: a data-op fired THIS turn is trusted over the store,
    which may not have caught up — the harness never contradicts it. `metrics` is the turn's LLM metrics, from
    which an oversized `widget_data` is recognised; pass None to skip that half.
    """
    if not may_escalate:
        return None
    try:
        from nucleo import harness
        goal = await harness.false_claim(spoken, data_done=data_done)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"harness skipped: {e}")
        goal = None
    if goal:
        req = ""
        try:
            req = harness.rescue_request(goal)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"harness request skipped: {e}")
        if req:
            return {"request": req, "reason": HARNESS, "goal": goal,
                    "surface": "documento" if goal.get("target") == "documento" else ""}
    head = None
    if metrics is not None:
        try:
            from nucleo.flash.fast_client import oversized_widget_write
            head = oversized_widget_write(metrics)
        except Exception:  # noqa: BLE001
            head = None
    if head:
        return {"request": (turn_text + " — [el turno de voz intentó escribir este contenido en un widget y NO "
                            "CABE en un turno: complétalo y entrégalo al widget documento con `append` por "
                            "secciones. Lo que empezaba a escribir: " + head + "…]"),
                "surface": "documento", "reason": OVERSIZED, "head": head}
    return None


async def mirror_probe(tool_calls: list, tags: list, spoken: str, turn_text: str, metrics=None) -> None:
    """The probe's half of the same decision (parallel impl, V2-252): the shown cards become goals and what
    the turn owes is synthesized as an `escalate_to_slowbrain` call, so the rest of the probe path (action
    classification, execution, ack) is the one a normal escalation takes. Never raises."""
    try:
        await_shown = [(t.get("extra") or {}).get("id") for t in (tags or []) if t.get("action") == "show"]
        note_shown(await_shown, turn_text)
        busy = any(t["name"] in ("escalate_to_slowbrain", "widget_data") for t in (tool_calls or []))
        owed = await rescue(spoken, data_done=False, turn_text=turn_text,
                            metrics=(None if tool_calls else metrics), may_escalate=not busy)
        if owed:
            tool_calls.append({"name": "escalate_to_slowbrain",
                               "args": {"request": owed["request"], "surface": owed["surface"]}})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"probe turn repairs skipped: {e}")


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


def holding_line(window, prev_pending: bool, *, after_filler: bool = False) -> str:
    """The neutral waiting sentence for a turn that escalated and said nothing (extracted V2-661).

    V2-029: with a background task ALREADY running when the turn began, the sentence varies («sigo con ello»)
    instead of repeating. V2-189: never the same phrase twice — `prev_pending` only told the first from the
    rest, so from the third on they were all identical (mirror of the probe, wire in BOTH). And if a filler
    already sounded this turn, the opener would restate it («Déjame que mire…» + «Vale, dame un momento»,
    measured 2026-09-09, session 2bdc67ee)."""
    try:
        from voice.engine.core import langs
        from nucleo.flash import router_guards
        return router_guards.holding_line(window, langs.current_language(), after_filler=after_filler)
    except Exception:  # noqa: BLE001
        return "Sigo con ello." if prev_pending else "Vale, dame un momento."


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
