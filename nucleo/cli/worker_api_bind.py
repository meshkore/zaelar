"""nucleo/cli/worker_api_bind.py — which waiting task does an utterance answer? A verdict of the turn's brief (V2-851 §3a).

While tasks wait for his answer, the brief carries ONE more declared question — «does this message answer one of the
open questions?» — whose choices are the open questions by `ask_id`, plus `none`. Read asymmetrically
(`nucleo/turn/verdicts`):

  · an `ask_id` at or above the LICENCE (0.5) binds the utterance to that question;
  · `none` at or above the VETO (0.85) binds nothing — it was a new request, a correction, a comment;
  · any other verdict is a doubt, and a doubt is ASKED: ASK_WHICH among the waiting tasks (an `ask` naming them);
  · no verdict at all (brief off, in flight, failed) binds only what the model itself routed (`answer_worker`), and
    only when one task waits — with several it is asked.

Never by length, never by a word list, never «the oldest». A screen answer needs none of this: it carries its
`ask_id` (`POST /api/tasks/{id}/answer`).
"""
from __future__ import annotations

KEY = "answers_open_question"
NONE = "none"
#: How many open questions ride in the brief (the choices of one question).
MAX_ASKS = 6

ANSWER, ASK_WHICH, NOTHING = "answer", "ask_which", "nothing"

#: The doubt we last asked (ASK_WHICH): his words that fitted several tasks, kept so the turn that names the task
#: passes THOSE words on, not «the first one». One doubt at a time; it expires.
_DOUBT: dict = {"text": "", "at": 0.0}
DOUBT_TTL_S = 300.0

INSTRUCTIONS = ("The assistant's background tasks have asked the operator questions and are WAITING for his answer "
                "(each choice names one question by its id). Does the operator's message, in any wording or language, "
                "ANSWER one of those questions — give the information or the decision it asked for? Pick that "
                "question's id. Answer 'none' when it answers none of them: a new request, a correction of something "
                "else, a counter-question, a comment, or a message about something else.")


def question(open_asks, last_reply: str = "") -> dict:
    """The brief's question, built from the open questions (`worker_api.open_asks()`); {} when nothing waits."""
    asks = list(open_asks or [])[:MAX_ASKS]
    if not asks:
        return {}
    criteria = {str(a["ask_id"]): (f"it answers «{str(a.get('question') or '')[:200]}»"
                                   + (f" (task «{str(a.get('title') or '')[:80]}»)" if a.get("title") else ""))
                for a in asks}
    criteria[NONE] = "it answers none of these questions"
    lr = (last_reply or "").strip()
    return {"instructions": INSTRUCTIONS + (f" [Our previous reply: {lr[:200]}]" if lr else ""), "criteria": criteria}


def bind(brief, *, model_answered: bool = False, asks=None) -> tuple[str, list]:
    """`(ANSWER, [ask])` · `(ASK_WHICH, asks)` · `(NOTHING, [])` for this turn. Never raises."""
    try:
        if asks is None:
            from nucleo.cli import worker_api
            asks = worker_api.open_asks()
        asks = list(asks or [])[:MAX_ASKS]
        if not asks:
            return NOTHING, []
        from nucleo.turn import verdicts
        choice, info = verdicts.read(brief, KEY, None, min_confidence=0.0)
        if not info or choice is None:
            if not model_answered:
                return NOTHING, []
            return (ANSWER, asks) if len(asks) == 1 else (ASK_WHICH, asks)
        conf = float(info.get("confidence") or 0.0)
        by_id = {str(a["ask_id"]): a for a in asks}
        if str(choice) in by_id and conf >= verdicts.LICENCE:
            return ANSWER, [by_id[str(choice)]]
        if str(choice) == NONE and conf >= verdicts.VETO:
            return NOTHING, []
        return ASK_WHICH, asks
    except Exception:  # noqa: BLE001 — a classifier may never break a turn; nothing is bound blind
        return NOTHING, []


def answer_text(text: str) -> str:
    """What the bound question receives: his words, preceded by the words our doubt was about when he is resolving it."""
    import time
    said = " ".join(str(text or "").split())
    prior, _DOUBT["text"] = _DOUBT["text"], ""
    if prior and time.time() - float(_DOUBT["at"]) <= DOUBT_TTL_S and prior != said:
        return f"{prior} — {said}"
    return said


def ask_which(asks, *, text: str = "") -> str:
    """Put the doubt to him: the `ask` event naming the waiting tasks (`among`), and the line Flash says."""
    import time
    _DOUBT.update(text=" ".join(str(text or "").split()), at=time.time())
    from i18n import langs
    from nucleo.cli import worker_api
    from nucleo.runtime_ids import next_seq
    titles = ", ".join(f"«{str(a.get('title') or a.get('question') or '')[:60]}»" for a in asks)
    line = str(getattr(langs.current_language(), "answer_which_task", "") or "").format(among=titles)
    worker_api.emit_ask(task_id="", ask_id=f"which-{next_seq('worker_api.which')}", text=line,
                        among=[a["task_id"] for a in asks])
    return line
