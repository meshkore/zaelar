"""nucleo/flash/death_line.py — a reply that promises a follow-up over an errand that just DIED says so.

Measured 2026-10-10 20:54 (use case `build-workout-tracker-widget__us`, text channel). The widget build died on a
transient rate limit at 20:54:38.6 — while the operator's «no rush» turn was in flight. Every death path fired:
`ended._remember_ended` pushed its note, `session._deliver` pushed its note AND `proactive.notify` (no live
speaker on the text channel) pushed a third. All three are notes for the NEXT turn — and that turn's prompt had
been composed before the death, so its reply came out 0.3 s later as «Building it in the background — I'll let
you know the moment it's ready». There was no next turn: the operator was left waiting on a promise over an
errand the system already knew was dead, with three undelivered notices in the mailbox.

The fact is known when the reply leaves (`ended.recently_ended_sessions`, with `told == 0`: no prompt has carried
it yet, so this reply was written blind to it). The sibling of `delivery.stalled_task_backstop`, for the same
reason — when the correct conduct is deterministic, code guarantees it, not temperature:

  · only on a WAITING reply (`delivery._WAITING_REPLY_RE`) — a reply that is already saying something else is
    left alone, and the notes still reach the next turn;
  · only for a death nobody has carried (`told == 0`), and silent if the reply already says it failed;
  · it is said ONCE: the ending is marked reported (`mark_death_reported`, the counter the prompt reads) and the
    three queued notes about it are retracted, so the next turn does not announce it a second time.

The sentence is the session's language (`i18n.langs`), and the reason is the A5 class in plain words.
"""
from __future__ import annotations

from loguru import logger

import re as _re

from .text_norm import _norm_txt

#: The reply already says it went wrong — appending the fact again would be the broken record.
_ALREADY_SAYS_RE = _re.compile(
    r"(fail|couldn'?t|could not|wasn'?t able|unable|didn'?t work|went wrong|broke|died|rate.?limit|"
    r"no pude|no he podido|fallo|ha fallado|fallad|murio|ha muerto|no salio|se ha roto|no ha funcionado)")

_WHY = {"rate": "death_why_rate", "credit": "death_why_credit", "auth": "death_why_auth",
        "network": "death_why_network", "stalled": "death_why_stalled"}
#: Classes a retry cannot fix from here — offering one would promise what will fail the same way.
_NEEDS_A_FIX = frozenset({"credit", "auth"})


def _lang():
    from i18n import langs as _lg
    return _lg.current_language()


def _dead_untold(rows) -> list[dict]:
    return [r for r in (rows or []) if str(r.get("status") or "") == "error" and not r.get("ok")
            and int(r.get("told") or 0) == 0]


def sentence(row: dict) -> str:
    """The plain-words line for one dead errand, in the session language."""
    spec = _lang()
    cls = str(row.get("error_class") or "")
    what = spec.death_what_widget if str(row.get("kind") or "") == "code" else spec.death_what_task
    why = getattr(spec, _WHY[cls]) if cls in _WHY else ""
    offer = spec.death_offer_fix if cls in _NEEDS_A_FIX else spec.death_offer_retry
    return spec.death_line.format(what=what, why=why, offer=offer).strip()


def backstop(reply: str, rows=None) -> str:
    """The sentence to APPEND to `reply`, or "". Marks the death told and retracts its queued notes. Never raises."""
    try:
        r = (reply or "").strip()
        if not r:
            return ""
        from .delivery import _WAITING_REPLY_RE
        n = _norm_txt(r).replace("’", "'")
        if not _WAITING_REPLY_RE.search(n) or _ALREADY_SAYS_RE.search(n):
            return ""
        from nucleo.workers import ended as _ended
        dead = _dead_untold(_ended.recently_ended_sessions(limit=5) if rows is None else rows)
        if not dead:
            return ""
        row = dead[0]
        tid = str(row.get("id") or "")
        line = sentence(row)
        _ended.mark_death_reported([tid])
        try:
            from voice import brain_notes as _bn
            for key in (f"death:{tid}", f"delivery:{tid}", f"notice:{tid}"):
                _bn.retract(key)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"death_line: queued notes not withdrawn — {type(e).__name__}: {e}")
        try:
            from voice.observer import emit
            emit("brain", "📬 death backstop: the waiting reply says the errand died", role="system",
                 extra={"id": tid, "error_class": str(row.get("error_class") or ""), "reply": r[:90]})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"death_line: emit failed — {type(e).__name__}: {e}")
        return line
    except Exception:  # noqa: BLE001
        return ""
