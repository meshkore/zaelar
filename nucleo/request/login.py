"""nucleo/request/login.py — does he ONLY ask to sign in to a site? A question of the turn's brief, never his words.

The close's login fallback (V2-022) opens the browser login when the model said it would connect him and called
nothing. Whether the turn asked for that was a regex over his sentence (`_LOGIN_INTENT_RE`: «conéctame», «inicia
sesión», «sign in»…), born of a small model that forgot `authenticate_web` — and corrected four times for the forms
it read wrong (a question about capability, a third-person narration, a reflexive). Every one of those was a reading
of the REQUEST, which is what the brief's model reads anyway, in any language (V2-857 phase 8).

So it is one more DECLARED question of the brief, asked with the others in the turn's one Jev call. It is paid every
turn (CRIT-K9): the fallback runs exactly when the model forgot its call, so the question cannot be asked «only when
the model called something». Without a sure verdict nothing is opened — the model's own `authenticate_web` and the
browser worker's need-login path remain. The SITE still comes from his words (`web_auth.fallback_site`): the verdict
says THAT he asks to sign in, not where.
"""
from __future__ import annotations

KEY = "login_only"
LOGIN, OTHER = "login", "other"

INSTRUCTIONS = ("Does the operator, in THIS message, only ask the assistant to sign him in to (or connect, or link) "
                "one of his accounts on a website, with nothing else to do there once he is in?")

CHOICES = {
    LOGIN: "he asks to be signed in to, connected to or linked with his account on a website, and asks for nothing "
           "to be done there afterwards",
    OTHER: "anything else: a task to do on the site once signed in, a question about whether or how the assistant "
           "can connect, a story about someone connecting, or no sign-in at all",
}


def question(_ctx=None) -> dict:
    """The brief's question: is this turn a pure sign-in order?"""
    return {"instructions": INSTRUCTIONS, "criteria": dict(CHOICES)}


def verdict(brief) -> tuple[str, float]:
    """(choice, confidence) as the brief read it — ("", 0.0) when unread, in flight or failed. Never raises."""
    try:
        from nucleo.turn import verdicts as _v
        choice, info = _v.read(brief, KEY, "", min_confidence=0.0) if brief else ("", None)
        return (str(choice or ""), float((info or {}).get("confidence") or 0.0)) if info else ("", 0.0)
    except Exception:  # noqa: BLE001 — an unreadable brief is no verdict
        return "", 0.0


def asked(brief) -> bool:
    """A SURE «he only asks to sign in» (≥ the licence: the verdict completes an act the model did not make)."""
    from nucleo.turn import verdicts as _v
    choice, conf = verdict(brief)
    return choice == LOGIN and conf >= _v.LICENCE
