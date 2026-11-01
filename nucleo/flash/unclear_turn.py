"""nucleo/flash/unclear_turn.py — a turn the fast model could not read gets ONE deliberate look (V2-833 F7).

THE DEFECT (operator's session, 2026-11-01). «…y lo pon pa tipos como tú de Shakira» reached the voice model as the
transcript of a song request with words swapped by the recogniser. The fast model — reasoning OFF, because a
reasoning model cannot keep a spoken conversation fluid — answered «I didn't catch that, say it again?», and nothing
in the engine could catch it: every repair fires on a PROMISE («I'll put it on» with no call), and a request to
repeat promises nothing. Measured on the exact messages of that turn: the same model with reasoning ON understood it
3 times out of 4, and acted on no comment («I love Shakira») in 4 out of 4.

THE MECHANISM. The fast model does not ask him to repeat any more: it says so as a CALL (`not_understood`, offered
every turn, in the `core` family), which is the structured half of the main request rather than a guess at its
words. The engine then:

  1. says one line of its own from the language table (`pondering_lines`, «let me think…») — separate from the
     lead-in fillers, because it announces thinking, not waiting;
  2. asks the SAME model once more, with reasoning on, the same messages plus a note to read it again, and the
     whole contextual catalogue — its calls go through the turn's own `on_tool_call`, the same gate as any call;
  3. speaks what that pass says, through the turn's tag seam; when it times out, fails or says nothing, says one
     `not_understood_lines` line: it did not understand, put it another way or give one more detail.

Bounded: only on a turn that made that call; one pass, under a wall (`ZAELAR_UNCLEAR_PASS_S`, default 10 s — one
reasoning call was measured hanging 358 s). Every other turn pays nothing and stays non-reasoning.
"""
from __future__ import annotations

import asyncio
import os

from loguru import logger

#: The brief's question (V2-833 F8): can what he wants be read from the sentence as it stands? Measured 2026-11-01 over the
#: bench's garbled, clear and remark lines, ×3: the garbled Shakira line `garbled` 0.82–0.85, stray syllables `noise`
#: 0.92–0.98, every clear order, question and remark `clear` — never a false `garbled`.
KEY = "readable"
CLEAR, GARBLED, NOISE = "clear", "garbled", "noise"
INSTRUCTIONS = ("This is a live speech-to-text transcript of what the operator just said to his voice assistant. Can "
                "what he wants be read from the sentence as it stands?")
CRITERIA = {
    CLEAR: "it reads as a request, a question, an answer or a remark — even casual, elliptical, slangy, in any "
           "language, or with one word off",
    GARBLED: "words are swapped, cut or missing as a speech recogniser leaves them, so the sentence does not read as "
             "it stands — but a request can still be guessed from it: an app, a song, a person or an action is named",
    NOISE: "no readable intent at all: stray syllables, sounds, or a fragment with nothing named",
}


def question(ctx: dict) -> dict:
    """The brief's entry. Our previous reply rides along, as in `request_type`: «yes, the second one» is clear only as
    an answer."""
    lr = str((ctx or {}).get("last_reply") or "").strip()
    return {"instructions": INSTRUCTIONS + (f" [Our previous reply: {lr[:200]}]" if lr else ""),
            "criteria": dict(CRITERIA)}


def verdict(brief) -> str:
    """`garbled` / `noise` when the brief read the sentence as unreadable, sure enough to license a pass the model did
    not make (`verdicts.LICENCE`); "" otherwise — unsure, in flight, off or clear: today's path."""
    try:
        from nucleo import jev
        from nucleo.turn import verdicts as _v
        choice, _info = jev.read(brief, KEY, "", min_confidence=_v.LICENCE)
        return choice if choice in (GARBLED, NOISE) else ""
    except Exception as e:  # noqa: BLE001
        logger.debug(f"unclear_turn: no verdict read ({e!r})")
        return ""


def holds(brief) -> bool:
    """Does this turn's verdict hold the fast pass's words until it is known whether the pass ACTED?"""
    return bool(verdict(brief))


#: The tools the deliberate pass is never offered: asking again would loop, and the escape hatch is moot because the
#: pass already gets the whole contextual catalogue.
_NOT_OFFERED = frozenset({"not_understood", "need_capability"})


def wall_s() -> float:
    try:
        return max(1.0, float(os.getenv("ZAELAR_UNCLEAR_PASS_S", "10")))
    except ValueError:
        return 10.0


def _lang():
    from i18n import langs
    return langs.current_language()


def _recent(window) -> list[str]:
    return [str((m or {}).get("content") or "").strip() for m in (window or [])
            if (m or {}).get("role") == "assistant"][-3:]


def pick(lines, window) -> str:
    """The first line of `lines` not said in the last three turns — rotation, never the same words twice running."""
    lines = [str(x) for x in (lines or ()) if str(x).strip()]
    if not lines:
        return ""
    recent = " ".join(_recent(window))
    return next((ln for ln in lines if ln not in recent), lines[0])


def with_note(messages: list[dict], note: str, heard: str = "") -> list[dict]:
    """The same messages, the operator's last line carrying the pass's note underneath. With `heard`, that line is HIS
    words alone: the notices the turn appended to it (pending system notices, the lead-in filler's note) belonged to
    the reflex pass — measured in the F8 bench, a pending «add_meeting saved without duration_min» notice made the
    deliberate pass rewrite the dentist appointment on a turn that asked for a song."""
    out = [dict(m) for m in (messages or [])]
    for m in reversed(out):
        if m.get("role") == "user":
            m["content"] = f"{(heard or '').strip() or m.get('content') or ''}\n\n{note}".strip()
            break
    return out


def pass_tools(catalog: list[dict]) -> list[dict]:
    return [t for t in (catalog or []) if (t.get("function") or {}).get("name") not in _NOT_OFFERED]


async def answer(*, messages, spec, catalog, on_tool_call, send, take, buf_reset, buf_add, emit,
                 speech, window, client_factory, said_before: str = "", readable: str = "",
                 heard: str = "", spoken: list | None = None) -> bool:
    """Run the deliberate look for a turn that called `not_understood`. Returns True when it ACTED (made a call).
    Never raises: whatever fails ends in the honest «I did not understand» line."""
    lang = _lang()
    calls: list[str] = []

    def _on_call(name, args):
        calls.append(name)
        on_tool_call(name, args)

    if readable == NOISE:
        # nothing was named: a deliberate pass has nothing to read — the honest line, with no «let me think» before it
        said = pick(getattr(lang, "not_understood_lines", ()), window)
        if said:
            send((" " if said_before.strip() else "") + said)
        emit("brain", "🤔 pasada deliberada: no actuó", role="system", text=said[:200],
             extra={"cat": "flash", "calls": [], "why": "noise"})
        return False
    ponder = pick(getattr(lang, "pondering_lines", ()), window)
    cover = ""
    if ponder:
        cover = (" " if said_before.strip() else "") + ponder + " "   # never glued to words the turn already said
        send(cover)
    emit("brain", "🤔 pasada deliberada: el turno no entendió la petición", role="system",
         extra={"cat": "flash", "said": ponder, "wall_s": wall_s()})
    text, why = "", ""
    try:
        text = await asyncio.wait_for(
            client_factory().complete(with_note(messages, str(getattr(lang, "unclear_pass_note", "") or ""), heard),
                                      spec=spec, tools=pass_tools(catalog), on_tool_call=_on_call,
                                      max_tokens=2000),
            timeout=wall_s())
    except asyncio.CancelledError:
        raise
    except asyncio.TimeoutError:
        why = "wall"
    except Exception as e:  # noqa: BLE001 — a failed pass is said, never raised
        why = f"error: {e!r}"[:160]
        logger.debug(f"unclear_turn: the deliberate pass failed ({e!r})")
    said = ""
    if text:
        buf_reset()
        buf_add(text)
        said = speech.sanitize(take(True), drop_metadata=False).strip()   # its inline tags still run
    if said and calls:
        # A pass that ACTED speaks through what the act ended in, never through words written before it ran (the turn's
        # rule, `nucleo/turn/reply.py`). F8 bench: «No te he entendido, ¿me lo repites?» while the song it had just
        # called started; «Suena «We Will Rock You»» read off the card before its own play landed.
        emit("brain", "🤐 pasada deliberada: actuó — sus palabras previas no se dicen", role="system", text=said[:160],
             extra={"cat": "flash", "calls": calls})
        said = ""
    if not said and calls and cover and spoken is not None and spoken and spoken[-1] == cover:
        # The cover is not the turn's words: a lane that speaks only when the model said nothing (the music receipt,
        # «Suena «X»») must still speak. F8 bench: «Déjame pensar…» and then silence while the song started.
        spoken.pop()
    if not said and not calls:
        said = pick(getattr(lang, "not_understood_lines", ()), window)
        why = why or "nothing"
    if said:
        send(said)
    emit("brain", "🤔 pasada deliberada: " + ("actuó" if calls else "no actuó"), role="system", text=said[:200],
         extra={"cat": "flash", "calls": calls, "why": why})
    return bool(calls)
