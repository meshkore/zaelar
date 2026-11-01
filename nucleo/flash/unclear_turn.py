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


def with_note(messages: list[dict], note: str) -> list[dict]:
    """The same messages, the operator's last line carrying the pass's note underneath."""
    out = [dict(m) for m in (messages or [])]
    for m in reversed(out):
        if m.get("role") == "user":
            m["content"] = f"{m.get('content') or ''}\n\n{note}".strip()
            break
    return out


def pass_tools(catalog: list[dict]) -> list[dict]:
    return [t for t in (catalog or []) if (t.get("function") or {}).get("name") not in _NOT_OFFERED]


async def answer(*, messages, spec, catalog, on_tool_call, send, take, buf_reset, buf_add, emit,
                 speech, window, client_factory, said_before: str = "") -> bool:
    """Run the deliberate look for a turn that called `not_understood`. Returns True when it ACTED (made a call).
    Never raises: whatever fails ends in the honest «I did not understand» line."""
    lang = _lang()
    calls: list[str] = []

    def _on_call(name, args):
        calls.append(name)
        on_tool_call(name, args)

    ponder = pick(getattr(lang, "pondering_lines", ()), window)
    if ponder:
        send((" " if said_before.strip() else "") + ponder + " ")   # never glued to words the turn already said
    emit("brain", "🤔 pasada deliberada: el turno no entendió la petición", role="system",
         extra={"cat": "flash", "said": ponder, "wall_s": wall_s()})
    text, why = "", ""
    try:
        text = await asyncio.wait_for(
            client_factory().complete(with_note(messages, str(getattr(lang, "unclear_pass_note", "") or "")),
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
        said = speech.sanitize(take(True), drop_metadata=False).strip()
    if not said and not calls:
        said = pick(getattr(lang, "not_understood_lines", ()), window)
        why = why or "nothing"
    if said:
        send(said)
    emit("brain", "🤔 pasada deliberada: " + ("actuó" if calls else "no actuó"), role="system", text=said[:200],
         extra={"cat": "flash", "calls": calls, "why": why})
    return bool(calls)
