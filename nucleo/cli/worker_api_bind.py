"""nucleo/cli/worker_api_bind.py — which waiting task does an utterance answer? A verdict of the turn's brief (V2-851 §3a).

While tasks wait for his answer, the brief carries ONE more declared question — «does this message answer one of the
open questions?» — whose choices are the open questions by `ask_id`, plus `none`. Read asymmetrically
(`nucleo/turn/verdicts`):

  · an `ask_id` at or above the LICENCE (0.5) binds the utterance to that question;
  · `none` at or above the VETO (0.85) binds nothing — it was a new request, a correction, a comment;
  · any other verdict is a doubt, and a doubt is ASKED: ASK_WHICH among the waiting tasks (an `ask` naming them) —
    with two or more waiting, `several` is the reader's own way to say the answer fits more than one;
  · no verdict at all (brief off, in flight, failed) binds only what the model itself routed (`answer_worker`), and
    only when one task waits — with several it is asked.

Never by length, never by a word list, never «the oldest». A screen answer needs none of this: it carries its
`ask_id` (`POST /api/tasks/{id}/answer`).
"""
from __future__ import annotations

KEY = "answers_open_question"
NONE = "none"
#: The declared doubt, offered when two or more questions wait: his answer fits more than one of them (battery C3,
#: 2026-11-05: «the first one» with two questions each offering a first candidate bound to the newest at 0.86 — no
#: choice let the reader say «either»). Chosen at or above the licence, it is ASKED, never bound.
SEVERAL = "several"
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


#: A choice that names one CANDIDATE of a question: `<ask_id>#<index>` — the door declared the candidates, so the
#: verdict picks among them (V2-851: «which Raquel» is the brief's reading, never a match of his words).
PICK = "#"


def _choices(a: dict) -> dict:
    q = str(a.get("question") or "")[:200]
    title = f" (task «{str(a.get('title') or '')[:80]}»)" if a.get("title") else ""
    cands = [str(c) for c in (a.get("candidates") or [])]
    if not cands:
        return {str(a["ask_id"]): f"it answers «{q}»{title}"}
    return {f"{a['ask_id']}{PICK}{i}": f"it answers «{q}»{title} choosing «{c[:80]}»" for i, c in enumerate(cands)}


def question(open_asks, last_reply: str = "") -> dict:
    """The brief's question, built from the open questions (`worker_api.open_asks()`); {} when nothing waits. A
    question whose door named its candidates offers one choice per candidate."""
    asks = list(open_asks or [])[:MAX_ASKS]
    if not asks:
        return {}
    criteria: dict = {}
    for a in asks:
        criteria.update(_choices(a))
    if len(asks) > 1:
        criteria[SEVERAL] = ("it fits more than one of these questions equally — what it gives (a position, a yes or "
                             "no, a value) is something more than one of them asks for, so which one it answers "
                             "cannot be told")
    criteria[NONE] = "it answers none of these questions"
    lr = (last_reply or "").strip()
    return {"instructions": INSTRUCTIONS + (f" [Our previous reply: {lr[:200]}]" if lr else ""), "criteria": criteria}


def bind(brief, *, model_answered: bool = False, asks=None) -> tuple[str, list]:
    """`(ANSWER, [ask])` · `(ASK_WHICH, asks)` · `(NOTHING, [])` for this turn. Never raises. A bound ask chosen by
    one of its candidates carries `choice` (the candidate's index). A sure choice whose question is no longer open
    (answered this turn by the act itself) binds nothing."""
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
            return (ANSWER, asks) if len(asks) == 1 and not asks[0].get("candidates") else (ASK_WHICH, asks)
        conf = float(info.get("confidence") or 0.0)
        by_id = {str(a["ask_id"]): a for a in asks}
        ask_id, _, idx = str(choice).partition(PICK)
        if ask_id in by_id and conf >= verdicts.LICENCE:
            a = by_id[ask_id]
            if not idx:
                return (ANSWER, [a]) if not a.get("candidates") else (ASK_WHICH, asks)
            if idx.isdigit() and int(idx) < len(a.get("candidates") or []):
                return ANSWER, [{**a, "choice": int(idx)}]
        if str(choice) == NONE and conf >= verdicts.VETO:
            return NOTHING, []
        if str(choice) == SEVERAL:
            return ASK_WHICH, asks
        if str(choice) != NONE and ask_id not in by_id and conf >= verdicts.LICENCE:
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
