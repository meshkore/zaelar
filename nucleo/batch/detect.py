"""Is this message a LIST of things to do, or one request? (V2-771)

Two stages, cheapest first, so an ordinary turn pays nothing:

1. **Shape.** Length, lines, enumeration, sentences — the geometry of the text, never its vocabulary. A table
   of verbs is not a router and is blind outside the Latin alphabet (V2-750); a numbered list looks like a
   numbered list in every language. Below the shape floor the answer is «one request» without asking anybody.
2. **Jev.** Past the floor, ONE Choice question decides. Shape alone cannot: a single detailed request («find me
   a flat in Madrid, three bedrooms, a terrace, near the metro, under 1 500…») is long and has many clauses,
   and it is ONE task. Jev reads what the clauses are FOR.

When Jev is off or fails, only an unmistakable shape (a long text with three or more enumerated items) counts
as a list; anything else stays one turn — today's path, which is the safe failure.
"""
from __future__ import annotations

import re

#: Below this a message is one request, whatever it says. A short «apúntame el dentista y llama a Pedro» is
#: two orders, and the turn already handles two orders (several tool calls in one reply); a list is what the
#: turn CANNOT hold.
MIN_CHARS = 280
#: Past this the shape floor is met by length alone (a pasted wall of text with no line breaks — voice).
LONG_CHARS = 900
#: How sure Jev must be before a message leaves the ordinary turn. A false «several» costs a split call and
#: a list of one step; a false «single» costs what it costs today. Asymmetric, so the bar is high.
MIN_CONFIDENCE = 0.7

_ENUM_RE = re.compile(r"^\s*(?:\d{1,2}\s*[.)\-:]|[-•*·▪︎]|[a-zA-Z]\s*[.)])\s+\S")
_SENTENCE_RE = re.compile(r"[.!?。！？]+(?:\s|$)")

QUESTION_KEY = "message_shape"
_INSTRUCTIONS = ("Does the user's message ask for ONE thing, however detailed, or hand over SEVERAL "
                 "independent things to do, set up or remember, each of which would be its own request?")
CRITERIA = {
    "single": "One request or one topic: a question, one order, one task with its details and constraints, "
              "or conversation",
    "several": "A list of several independent things: setup steps, facts to remember, appointments to create, "
               "errands or searches — each one its own task",
}


def shape(text: str) -> dict:
    """The geometry of the message: chars, non-empty lines, enumerated lines, sentences."""
    t = (text or "").strip()
    lines = [ln for ln in t.splitlines() if ln.strip()]
    return {"chars": len(t), "lines": len(lines),
            "enumerated": sum(1 for ln in lines if _ENUM_RE.match(ln)),
            "sentences": len(_SENTENCE_RE.findall(t + " "))}


def could_be_a_list(text: str) -> bool:
    """The shape floor. False means «one request» with certainty and nothing else is asked."""
    s = shape(text)
    if s["chars"] < MIN_CHARS:
        return False
    if s["chars"] >= LONG_CHARS:
        return True
    return s["enumerated"] >= 3 or s["lines"] >= 4 or s["sentences"] >= 4


def unmistakable(text: str) -> bool:
    """A shape no single request has: long, and three or more enumerated items. The fallback when Jev is off."""
    s = shape(text)
    return s["chars"] >= 400 and s["enumerated"] >= 3


def ask(text: str) -> dict | None:
    """Jev's verdict on the message, or None when it could not be asked. Blocking — call it in a thread."""
    try:
        from nucleo import jev
        # The verdict needs the SHAPE, not every word: the head and the tail of a long paste carry it, and a
        # 4 000-char state is a slower question for no better answer.
        t = (text or "").strip()
        state = t if len(t) <= 3000 else t[:2000] + "\n…\n" + t[-800:]
        return jev.choose_sync(QUESTION_KEY, state, instructions=_INSTRUCTIONS, criteria=CRITERIA,
                               question_id="message-shape")
    except Exception:  # noqa: BLE001 — a classifier never breaks a turn
        return None


def is_a_list(text: str) -> tuple[bool, dict]:
    """(is it a list?, why). Never raises; every doubt answers «no», which is today's path."""
    if not could_be_a_list(text):
        return False, {"by": "shape"}
    verdict = ask(text)
    if verdict and verdict.get("choice"):
        several = verdict["choice"] == "several" and float(verdict.get("confidence") or 0) >= MIN_CONFIDENCE
        return several, {"by": "jev", "choice": verdict["choice"],
                         "confidence": round(float(verdict.get("confidence") or 0), 2)}
    return unmistakable(text), {"by": "shape-fallback"}
