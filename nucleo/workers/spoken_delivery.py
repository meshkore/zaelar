"""nucleo/workers/spoken_delivery.py — what a finished errand SAYS, as opposed to what it wrote.

Demo pass 36 (2026-09-29): the monitor errand's closing summary was read out verbatim — a full report with
headings and bold, in Spanish, into an English session — about two and a half minutes of monologue. The next
two replies waited behind it and came out a turn late. A worker writes its summary for the sheet and the
brain; it is not a line to speak. The result is already on screen, so the voice says what came of it, briefly,
in the language the personal agent was set up in — whatever language the worker happened to write in.

The line is composed by the same fast model the conversation uses (one call, bounded). If that call does not
come back in time, the voice says the summary's opening instead, clipped — never the whole report.
"""
from __future__ import annotations

import re

from loguru import logger

_TIMEOUT_S = 6.0
#: False inside the test suite (root conftest): a deterministic test that reaches this composer would otherwise call a
#: paid model and hear its words instead of the summary it asserts on.
LIVE = True
_MAX_CHARS = 280


def _language() -> str:
    try:
        from i18n.langs import current_language
        lang = current_language()
        return f"{lang.name} ({lang.native})" if lang.native and lang.native != lang.name else lang.name
    except Exception:  # noqa: BLE001
        return ""


def _messages(goal: str, summary: str, ok: bool, verdict: str = "") -> list[dict]:
    lang = _language()
    in_lang = f"Say it in {lang}." if lang else "Say it in the language of the request."
    # V2-776 L3 — the outcome sentence is the CIRCUIT's verdict, never the worker's `ok`: «done» only over met,
    # «done, unverified» over an end state nobody could read, «what is missing» over a gave-up ending.
    from nucleo import circuit as _circuit
    outcome = _circuit.outcome_line(verdict, ok)
    rules = _circuit.voice_rules_line()
    # Demo pass 62, T1: «johnny, plan a five day trip…» was delivered as «Johnny, the three trip plans…» — the
    # errand opens with the ASSISTANT's name, and the composer took it for the person's.
    names = ""
    try:
        from nucleo.flash import presence as _presence
        own = [n for n in _presence.assistant_names() if n]
        if own:
            names = (f"\nYOUR own name is {own[0].title()}: when the errand opens with it, he was calling you — never "
                     "call him by it.")
    except Exception:  # noqa: BLE001
        names = ""
    return [
        {"role": "system",
         "content": (
             "You are a personal voice assistant telling your person that an errand they gave you has finished. "
             f"{outcome} Its full result is already on their screen.\n"
             f"Return ONLY what you will say out loud: at most two short spoken sentences. {in_lang}\n"
             "Name the outcome with its one or two most useful facts (the pick and its price, the date, the "
             "place). No markdown, no lists, no headings, no links, no symbols to read out."
             + names + (f"\n{rules}" if rules else ""))},
        {"role": "user", "content": f"Errand: {(goal or '').strip()[:400]}\n\nWorker's report:\n{summary[:3000]}"},
    ]


def clipped(summary: str) -> str:
    """The summary's opening, as speech: its first sentences up to `_MAX_CHARS`, markup dropped."""
    from voice import speech
    text = speech.sanitize(summary or "") or ""
    if len(text) <= _MAX_CHARS:
        return text
    out = ""
    for s in re.split(r"(?<=[.!?…])\s+", text):
        if out and len(out) + len(s) + 1 > _MAX_CHARS:
            break
        out = f"{out} {s}".strip()
    return out or text[:_MAX_CHARS].rsplit(" ", 1)[0]


async def line(goal: str, summary: str, *, ok: bool = True, verdict: str = "", timeout: float = _TIMEOUT_S) -> str:
    """The spoken line for a finished errand — composed in the agent's language, or `clipped(summary)`."""
    if not (summary or "").strip():
        return ""
    if not LIVE:
        return clipped(summary)
    try:
        import asyncio

        from nucleo.errand_title import _spec_for_naming
        from nucleo.flash.fast_client import FastClient
        spec = _spec_for_naming()
        if spec is not None:
            out = await asyncio.wait_for(
                FastClient().complete(_messages(goal, summary, ok, verdict), spec=spec, max_tokens=160, no_thinking=True),
                timeout=timeout)
            said = " ".join(str(out or "").split())
            from nucleo.flash import outgoing_lang as _ol   # «Ya está en tu pantalla…» to an English session (V2-781)
            if said and _ol.foreign_to_session(said):
                said = await _ol.said_in_session_language(said)
            if said:
                return said[: _MAX_CHARS * 2]
    except Exception as e:  # noqa: BLE001
        logger.info(f"spoken_delivery: no composed line ({str(e)[:80]}) — the summary's opening is said")
    return clipped(summary)
