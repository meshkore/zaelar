"""nucleo/flash/unclear_turn.py — a turn the fast model could not read is ANSWERED with a question, never re-run.

THE DEFECT (operator's session, 2026-11-01). «…y lo pon pa tipos como tú de Shakira» reached the voice model as the
transcript of a song request with words swapped by the recogniser. The fast model — reasoning OFF, because a
reasoning model cannot keep a spoken conversation fluid — answered «I didn't catch that, say it again?», and nothing
in the engine could catch it.

THE MECHANISM. «Unreadable» is a STATE of the turn, not a sentence the model may or may not say: the turn brief asks
whether the sentence can be read at all (`readable`: clear · garbled · noise — `KEY`, `question`, `verdict`), in the
one Jev trip the turn already pays. Under a sure unreadable verdict the reflex pass's words are held from the first
word (`follow_up_pass.Hold`); a pass that made an ACT read him after all and keeps its words, one that called nothing
— or only read (`READS`) — is dropped unsaid. The model's own `not_understood` call (offered every turn, `core`) is
the second reader of the same state. Either way the turn says ONE `not_understood_lines` line (`line`): it did not
understand, put it another way or give one more detail.

V2-833 F7 used to follow that with a DELIBERATE pass — the same model once more, reasoning on — which understood the
Shakira line 3 times out of 4. V2-851 F5 removed it with every model re-run after the main stream (target: zero):
Flash asks until it is clear (§2b of the plan), and his next sentence is a new turn with a fresh brief.
"""
from __future__ import annotations

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


#: The calls that are not acts: saying it could not read him, reading memory or a card. A reflex pass that only made
#: these on an unreadable sentence has not shown it read it — its words still go unsaid.
TOOL = "not_understood"


def _reads() -> frozenset:
    """Built from the DECLARED names, never a list of words: the router's read routes and the model's own mark."""
    from nucleo.flash import router as _router
    return frozenset({TOOL, _router.RECALL, _router.READ_WIDGET})


READS = _reads()


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


def line(window, said_before: str = "") -> str:
    """The one line an unreadable turn answers with — from the language table, rotated, never glued to words the turn
    already said. "" when the table has none (the turn's mute backstop speaks then)."""
    said = pick(getattr(_lang(), "not_understood_lines", ()), window)
    return ((" " if (said_before or "").strip() else "") + said) if said else ""
