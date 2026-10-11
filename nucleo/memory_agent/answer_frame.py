"""nucleo/memory_agent/answer_frame.py — a bare answer reaches the distiller WITH the question it answers.

Measured in `rental-car-automatic-airport__us` (2026-10-11). The introduction phase asked «where are you based?»,
he answered «San Francisco», and the distiller — which sees only the operator's turn — read the two words alone, in
the middle of a car-rental errand at Denver airport, as a trip: «Plans to travel to San Francisco the week of 12
October», and even «Asked the assistant to find an automatic rental car at San Francisco airport». `state.location`
stayed empty, so the introduction pack kept listing «where he lives» as unknown, and eight turns later the agent
asked again. His reply: «San Francisco, I said that earlier.»

Nothing was wrong with the slot machinery (`memory/slots.py` files a location pill into `state.location`); the
distiller was simply never told what the words were an answer TO. This module gives it that, and only that: when
the turn is short, is not itself a question, and the agent's previous reply ended by asking something, the
question travels in front of the answer. What the answer MEANS stays the distiller's reading — no slot is guessed
here, so a «San Francisco» after «where are you flying to?» still comes out a trip.
"""
from __future__ import annotations

import re
import time

#: A reply longer than this is saying something of its own, not answering a question.
_MAX_ANSWER_WORDS = 6
#: The previous reply only frames this turn while it is still the conversation's last word.
_MAX_AGE_S = 15 * 60
_MAX_QUESTION_CHARS = 160

_SENTENCE_RE = re.compile(r"[^.!?¿¡]*[¿]?[^.!?¿¡]*\?")


def _last_question(reply: str) -> str:
    """The question the reply ENDS on ("" if it ends on anything else)."""
    r = " ".join(str(reply or "").split())
    if not r.rstrip().endswith("?"):
        return ""
    found = _SENTENCE_RE.findall(r)
    q = (found[-1] if found else r).strip(" ,;:—-")
    return q[-_MAX_QUESTION_CHARS:]


def asked_before(*, now: float | None = None) -> str:
    """The question the agent's last reply ended on, if it is recent. "" otherwise, and on any read error."""
    try:
        from memory import api as _mem
        window = _mem.recent_window(limit=1) or []
    except Exception as e:  # noqa: BLE001 — a frame that cannot be read leaves the turn as it was
        from loguru import logger
        logger.debug(f"answer_frame: window unreadable ({e!r})")
        return ""
    last = next((m for m in reversed(window) if (m or {}).get("role") == "assistant"), None)
    if not last:
        return ""
    ts = float(last.get("ts") or 0)
    if ts and ((now or time.time()) - ts) > _MAX_AGE_S:
        return ""
    return _last_question(str(last.get("content") or ""))


def framed(text: str, *, asked: str | None = None) -> str:
    """`text` as the distiller should read it: unchanged, or prefixed with the question it answers."""
    t = str(text or "").strip()
    if not t or "?" in t or len(t.split()) > _MAX_ANSWER_WORDS:
        return text
    q = asked_before() if asked is None else _last_question(asked)
    if not q:
        return text
    return f"(answering the assistant's question «{q}») {t}"
