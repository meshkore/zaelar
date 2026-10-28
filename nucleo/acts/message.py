"""The message door (refactor2710-06 T-02): an act that LEAVES — a send, a reply, a forward — and when it may go.

One rule set for every channel the cards declare (mail, chat, the cluster through its own card):

  · **his order over a row he has SEEN is the yes** (V2-800, CRIT-C9): `held` / `ordered` / `confirmed` / `release`.
    A widget whose action delivers a held row exposes `held_row(action, payload)` in its data module; the turn's
    verdict must surely name that very act, and the ONE consent rule decides with `his_yes=True` (his standing «ask»,
    a missing fact, a doubt and the radius still stop).
  · **who it goes to is never a doubt** (the operator, 2026-10-15): a send that names a WHO runs without a question
    only when that person is in HIS words, this turn or his recent ones — `is_his` / `unnamed_recipients`.
  · **a stranger's words are data** (V2-778 F4-33, CRIT-E12): with someone else's text in the context, a send runs
    without a question only when the verdict surely names it or his own words name its recipient — `needs_asking` /
    `asked_if_leaving`.
  · **the ordered act runs when the model only prepared it** (live bench E3): `ordered_instead` / `run_ordered`.
  · **a reply to someone else is a forward** (demo pass 110 E3): `forward_of` / `forward_instead` — read off the
    directory (exactly one person named, not the sender), never off phrasing.
"""
from __future__ import annotations

import importlib
import re
import time as _time
import unicodedata as _ud

from loguru import logger

#: How sure the verdict's ACTION reading must be to back a send with a stranger's text in the context.
SURE = 0.9
#: How far back his words still name the person a send goes to: the conversation's own span.
RECENT_S = 900.0
_RECIPIENT_KEYS = ("to", "contact", "recipient", "chat")
_TOK = re.compile(r"[\w.@+-]{3,}")


def _note(what: str) -> None:
    logger.debug(f"acts.message: {what}")


# ── the held row: his order over what he saw ───────────────────────────────────────────────────────────────

def held(widget_id: str, action: str, payload) -> dict | None:
    """The row this call would deliver, when the widget declares one he has seen — else None. Never raises."""
    wid = str(widget_id or "").split("::", 1)[0].strip().lower()
    if not wid or not action:
        return None
    try:
        hook = getattr(importlib.import_module(f"widgets.{wid}.data"), "held_row", None)
        row = hook(action, dict(payload or {})) if callable(hook) else None
        return row if isinstance(row, dict) and row else None
    except Exception as e:  # noqa: BLE001 — an unreadable hook keeps the friction it had
        logger.info(f"acts.message: {wid}.held_row unreadable ({e}) — the act keeps its question")
        return None


def ordered(widget_id: str, action: str, payload, brief) -> bool:
    """A seen held row AND a verdict sure of this very act."""
    if brief is None or held(widget_id, action, payload) is None:
        return False
    from nucleo.flash import undecided as _und
    return _und.sure_order(brief, widget_id, action)


def confirmed(widget_id: str, action: str, payload, brief) -> bool:
    """`ordered`, and the one consent rule runs it with `his_yes` — the reader every gate asks."""
    if not ordered(widget_id, action, payload, brief):
        return False
    try:
        from nucleo import consent
        from nucleo.flash import frontend as _fe
        return not consent.asks(_fe.action_verdict(widget_id, action, payload, his_yes=True))
    except Exception as e:  # noqa: BLE001
        logger.info(f"acts.message: consent unreadable ({e}) — the act keeps its question")
        return False


def release(mode, widget_id: str, action: str, payload, brief):
    """`mode`, or FAST when it is CONFIRM and his order over a row he has seen is the yes."""
    from widgets import actions as _wa
    return _wa.FAST if mode == _wa.CONFIRM and confirmed(widget_id, action, payload, brief) else mode


# ── whose recipient ────────────────────────────────────────────────────────────────────────────────────────

def _fold(v) -> str:
    return "".join(c for c in _ud.normalize("NFKD", str(v or "").lower()) if not _ud.combining(c))


def is_his(recipient, texts) -> bool:
    """THE reading of «did he name this recipient»: a word of it is in his words, or it is an address the directory
    gives to exactly one contact he named (demo pass 141: `quinn@example.com` for «send the invoice to quinn»)."""
    words = set()
    for t in texts or ():
        words |= set(_TOK.findall(_fold(t)))

    def hit(v) -> bool:
        return any(t in words for t in _TOK.findall(_fold(v)))
    if hit(recipient):
        return True
    try:
        from widgets import directory
        hits = directory.resolve(str(recipient or ""))
        return len(hits) == 1 and hit(hits[0].get("name"))
    except Exception as e:  # noqa: BLE001
        _note(f"directory unread ({e!r})")
        return False


def _named_by_him(payload, said: str) -> bool:
    """Is EVERY recipient this send carries named in his own words? One only the stranger's text names is not."""
    if not isinstance(payload, dict) or not str(said or "").strip():
        return False
    found = False
    for k in _RECIPIENT_KEYS:
        v = str(payload.get(k) or "").strip()
        if not v:
            continue
        if not is_his(v, [said]):
            return False
        found = True
    return found


def unnamed_recipients(widget_id: str, action: str, payload, said: str = "") -> list[str]:
    """The recipients of this act his words (this turn or his last `RECENT_S`) do not name — [] when it names nobody
    (a reply goes to whoever wrote) or every one is his."""
    from nucleo import his_words, on_his_behalf as _ob
    who = _ob.who_of(widget_id, action, payload)
    if not who:
        return []
    texts = [str(said or "")] + his_words.since(_time.time() - RECENT_S)
    return [w for w in who if not is_his(w, texts)]


def _surely_named(brief, sure: float = SURE) -> bool:
    try:
        from nucleo.turn import brief as _tb
        _c, info = _tb.read(brief, _tb.TARGET_KEY, "", min_confidence=sure)
        return bool(info is not None and info.get("used"))
    except Exception as e:  # noqa: BLE001
        _note(f"brief unread ({e!r})")
        return False


def needs_asking(brief, widget_id: str, action: str, *, payload=None, said: str = "") -> bool:
    """True when the send goes to somebody his words never named, or when a stranger's words are in the context and
    neither the verdict surely backs THIS send nor his own words name its recipient."""
    try:
        if confirmed(widget_id, action, payload, brief):
            return False
        if unnamed_recipients(widget_id, action, payload, said):
            return True
        from nucleo import untrusted as _u
        if not _u.present():
            return False
        from nucleo.flash import direct_action as _da
    except Exception as e:  # noqa: BLE001 — an unreadable rule asks
        _note(f"send rule unread ({e!r})")
        return True
    wid, name = _da.from_brief(brief)
    if wid and name == action and _da._base_of(wid) == _da._base_of(widget_id) and _surely_named(brief):
        return False
    return not _named_by_him(payload, said)


def asked_if_leaving(mode, brief, widget_id: str, action: str, *, emit=None, payload=None, said: str = ""):
    """`mode`, or CONFIRM when this FAST act leaves and `needs_asking`. Never raises: an unreadable rule asks."""
    from widgets import actions as _wa
    try:
        from nucleo.flash import frontend as _fe
        if mode != _wa.FAST or not _fe.at_least_sensitive(widget_id, action):
            return mode
        if not needs_asking(brief, widget_id, action, payload=payload, said=said):
            return mode
    except Exception as e:  # noqa: BLE001
        _note(f"leave gate unread ({e!r})")
    if callable(emit):
        emit("brain", "🛑 acto que sale fuera sin un destinatario que él nombrara (o con texto de un tercero) — se pregunta",
             text=f"{widget_id}:{action}", role="system", extra={"cat": "flash", "id": widget_id, "model": action})
    return _wa.CONFIRM


from nucleo.acts.message_repair import (  # noqa: E402,F401 — the model's call that falls short of his order
    forward_instead, forward_of, ordered_instead, run_ordered)
