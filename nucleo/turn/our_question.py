"""His answer to a question the PHASE asked is his business with us, never an order for a live errand.

search-restaurant-occasion EN (2026-10-14). «Find me a restaurant for an anniversary in Portland…» was running when
the introduction pack rode a free turn and the reply asked «While that runs: where are you based these days?». He
answered «San Francisco. ok, let me know when you have options»; the reply promised to keep going, so
`promised_refinement` read his sentence as a refinement of the Portland errand and injected it whole. The worker
pivoted to San Francisco, the sheet's hard criteria said «In San Francisco», and he had to say «I asked for
Portland… the dinner is in Portland, not here».

The mechanism is the turn's own history, not his vocabulary: when the turn BEFORE his rode a phase pack
(`context_packs.ridden`) and its reply asked something, the short first sentence of his reply is the answer to
that question — it goes to the memory (which is where «where he lives» belongs) and is cut from what a live errand
hears. The rest of his sentence still routes as before.
"""
from __future__ import annotations

import re

#: An answer to «where are you based?» or «what's your name?» is a few words; past this it is saying something else.
_MAX_ANSWER_WORDS = 6
_SENTENCES = re.compile(r"(?<=[.!?;])\s+")


def last_question(reply: str) -> str:
    """The question the reply asked in its last two sentences ("" when it asked none there)."""
    parts = [p for p in _SENTENCES.split(" ".join(str(reply or "").split())) if p.strip()]
    return next((p for p in reversed(parts[-2:]) if "?" in p), "")


def previous_reply(spoken: str = "") -> str:
    """Our reply before this turn's (`spoken`), from the conversation memory both channels write. "" if none."""
    try:
        from memory import api as _mem
        window = _mem.recent_window(limit=3) or []
    except Exception as e:  # noqa: BLE001 — no window: nothing is cut
        from loguru import logger
        logger.debug(f"our_question: window unreadable ({e!r})")
        return ""
    now = " ".join(str(spoken or "").split())
    for m in reversed(window):
        said = " ".join(str((m or {}).get("content") or "").split())
        if (m or {}).get("role") == "assistant" and said and said != now:
            return said
    return ""


def without_its_answer(operator_text: str, spoken: str = "", *, asked: str | None = None, quiet: bool = False) -> str:
    """`operator_text` without the answer to the question our phase asked on the turn before. Unchanged when no
    pack rode that turn, its reply asked nothing, or his first sentence is not a short answer."""
    text = str(operator_text or "").strip()
    if not text:
        return text
    from nucleo.context_packs import ridden as _ridden
    if not _ridden.before(text):
        return text
    q = last_question(previous_reply(spoken) if asked is None else asked)
    if not q:
        return text
    parts = [p for p in _SENTENCES.split(text) if p.strip()]
    first = parts[0] if parts else ""
    if "?" in first or len(first.split()) > _MAX_ANSWER_WORDS:
        return text
    rest = " ".join(parts[1:]).strip()
    if not quiet:
        _emit(first, q)
    return rest


def _emit(answer: str, question: str) -> None:
    try:
        from voice.observer import emit
        emit("brain", "🙋 his answer to our phase's question stays out of the errand", role="system",
             extra={"cat": "flash", "answer": answer[:80], "question": question[:120]})
    except Exception as e:  # noqa: BLE001
        from loguru import logger
        logger.debug(f"our_question: emit failed ({e!r})")
