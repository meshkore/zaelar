"""nucleo/flash/capability_gap.py — a request for a capability no card declares is answered «not yet», never a worker.

V2-807 T-16. He asked the mail card to mirror his provider in real time. No card and no connector declares that.
The model promised it anyway, a promise backstop turned the promise into an errand, and a Brain Worker spent seven
minutes reading the mail card, operating its folders and reading another card's files, looking for a switch that
does not exist. A worker cannot add a capability to the product: what it can do is improvise against the cards'
own controls, which is exactly what he forbade («the widgets are not yours to touch, least of all the native ones»).

THE RULE. When the turn's verdict says, SURE, that the order asks one of our own cards or connectors to do
something none of their DECLARED actions does, the escalation portal (`escalate.escalate_to_slowbrain`, the one
door every errand passes) does not start the errand: he hears an honest «not yet», and the request is kept as a
suggestion. The decision is a verdict over the declarations (the open cards' declared actions, or the catalogue's
declared cards), asked inside the turn brief that is already paid for — never a list of words.

Only turn-born errands are judged (`src` voice/probe), because only those carry this turn's verdict; a relay, a
resume or a worker's own child continues work that already passed this door. Unsure, missing, failed or stale
verdict: today's path, unchanged — a missed errand is worse than an unasked question.
"""
from __future__ import annotations

import logging
import threading
import time

log = logging.getLogger(__name__)


def _note(where: str, exc: Exception) -> None:
    """Every degraded path here is fail-soft (nothing refused, nothing sent): say which one, never silently."""
    log.info("capability_gap: %s failed: %s", where, exc)

KEY = "capability_gap"
MISSING, DECLARED, WORK = "missing", "declared", "work"

INSTRUCTIONS = (
    "The operator asks the assistant for something. The assistant's own cards and connectors can do ONLY what they "
    "declare (listed below). Answer 'missing' ONLY when he asks one of THOSE listed cards or connectors to behave in "
    "a way none of their declared actions does: a feature, a setting, a filter, a sync or update mode, an "
    "integration that existing card does not have. Answer 'declared' when a declared action does it, or when he "
    "only talks, asks or answers. Answer 'work' when it is real work: searching or comparing on the web, a "
    "website, a booking, writing a document — and ALWAYS when he asks to build, create or program a NEW card or "
    "widget, or to change how a card looks: building cards is work the assistant does.")

CRITERIA = {
    MISSING: "he asks one of the assistant's own cards or connectors for a capability none of their declared "
             "actions provides — a change to the product itself",
    DECLARED: "a declared action of a card does it, or the turn is talk, a question or an answer",
    WORK: "real work: web research, a website, a booking, writing a document, or building a NEW card/widget or "
          "restyling one",
}

#: Turn-born errands carry this turn's verdict; nothing else does.
TURN_SOURCES = ("voice", "probe")
MAX_CARDS = 8
MAX_ACTIONS_PER_CARD = 40
MAX_DESC_CHARS = 90
#: A brief outlives its turn only briefly: an errand born later than this is not this turn's.
_BRIEF_TTL_S = 120.0


def _declarations(open_ids) -> str:
    """What the product can do, as the widgets declare it: the open cards' actions, or the catalogue's cards."""
    lines: list[str] = []
    ids = [str(w).split("::", 1)[0].strip().lower() for w in (open_ids or []) if str(w or "").strip()]
    try:
        from nucleo.flash import frontend as _fe
        for wid in list(dict.fromkeys(ids))[:MAX_CARDS]:
            acts = []
            for name, spec in list((_fe.declared_actions(wid) or {}).items())[:MAX_ACTIONS_PER_CARD]:
                desc = str((spec if isinstance(spec, dict) else {}).get("desc") or "").strip()
                acts.append(f"{name}" + (f" ({desc[:MAX_DESC_CHARS]})" if desc else ""))
            if acts:
                lines.append(f"Card «{wid}» declares: " + "; ".join(acts))
    except Exception as e:  # noqa: BLE001
        _note('declared actions of open cards', e)
        pass
    if not lines:
        try:
            from widgets import runtime as _rt
            for w in _rt.catalog()[:60]:
                wid = str(w.get("id") or "").strip()
                if not wid:
                    continue
                desc = str(w.get("description") or w.get("desc") or "").strip()
                names = ", ".join(list((w.get("actions") or {}).keys())[:MAX_ACTIONS_PER_CARD]) \
                    if isinstance(w.get("actions"), dict) else ""
                lines.append(f"Card «{wid}»" + (f" — {desc[:MAX_DESC_CHARS]}" if desc else "")
                             + (f" — actions: {names}" if names else ""))
        except Exception as e:  # noqa: BLE001
            _note('catalogue declarations', e)
            pass
    return "\n".join(lines)


def question(open_ids=None) -> dict | None:
    """The brief question, or None when nothing is declared to judge against (then nothing can be «missing»)."""
    decl = _declarations(open_ids)
    if not decl:
        return None
    return {"instructions": f"{INSTRUCTIONS}\n{decl}", "criteria": dict(CRITERIA)}


#: Refusing an errand is the expensive direction to be wrong in, so it asks for more than the house floor.
MIN_CONFIDENCE = 0.7


def missing(brief) -> bool:
    """The brief said, SURE, that the order asks for a capability no card declares."""
    try:
        from nucleo.turn import brief as _tb
        choice, info = _tb.read(brief, KEY, "", min_confidence=MIN_CONFIDENCE)
        return info is not None and str(choice or "") == MISSING
    except Exception as e:  # noqa: BLE001
        _note('reading the verdict', e)
        return False


# ── which brief belongs to the errand at the portal ─────────────────────────────────────────────────────────────
# The portal is reached from a dozen callers and none of them hands it the brief; the TRACE is what joins an
# errand to the turn that fired the brief (the same join the timeline uses). Bounded and fail-soft.
_LOCK = threading.Lock()
_BY_TRACE: dict[str, tuple[float, object]] = {}
_MAX_REMEMBERED = 32


def remember(handle, trace: str = "") -> None:
    """Called where a turn's brief is stamped: this trace's verdicts are THIS handle."""
    t = str(trace or "")
    if not t or handle is None:
        return
    with _LOCK:
        _BY_TRACE[t] = (time.time(), handle)
        if len(_BY_TRACE) > _MAX_REMEMBERED:
            for k, _v in sorted(_BY_TRACE.items(), key=lambda kv: kv[1][0])[: len(_BY_TRACE) - _MAX_REMEMBERED]:
                _BY_TRACE.pop(k, None)


def brief_of(trace: str):
    t = str(trace or "")
    if not t:
        return None
    with _LOCK:
        got = _BY_TRACE.get(t)
    if not got or time.time() - got[0] > _BRIEF_TTL_S:
        return None
    return got[1]


def _trace_of(ctx: dict) -> str:
    t = str((ctx or {}).get("trace") or "")
    if t:
        return t
    try:
        from voice import trace as _trace
        return _trace.current() or ""
    except Exception as e:  # noqa: BLE001
        _note('current trace', e)
        return ""


def refuses(request: str, ctx: dict | None) -> bool:
    """At the portal: is this a turn-born errand whose turn asked for a capability no card declares?"""
    c = dict(ctx or {})
    if str(c.get("src") or "") not in TURN_SOURCES or c.get("confirmed") or c.get("kind") == "dev":
        return False
    return missing(brief_of(_trace_of(c)))


def refuse(request: str) -> None:
    """Say it, show it, keep it: «not yet» to him, a row on the timeline, and the request as a suggestion."""
    req = (request or "").strip()
    noted = keep_as_suggestion(req)
    try:
        from voice.observer import emit
        emit("task", "blocked", role="system", text=req[:120],
             extra={"reason": "capability_gap", "kind_diag": "capability_gap", "suggestion": noted,
                    "cat": "flash"})
    except Exception as e:  # noqa: BLE001
        _note('timeline row', e)
        pass
    line = not_yet_line(noted)
    if not line:
        return
    try:
        import asyncio

        from voice import proactive
        asyncio.get_running_loop().create_task(proactive.notify("zaelar", line))
    except Exception as e:  # noqa: BLE001 — no loop (tests, boot): the timeline row above already records it
        _note('spoken not-yet line', e)
        pass


def not_yet_line(noted: bool) -> str:
    """His language's «not yet», saying where the request went — never an id, never a card's internals."""
    try:
        from i18n import langs as _langs
        lg = _langs.current_language()
        return str(getattr(lg, "capability_not_yet_noted" if noted else "capability_not_yet", "") or "")
    except Exception as e:  # noqa: BLE001
        _note('not-yet line language', e)
        return ""


def keep_as_suggestion(request: str) -> bool:
    """The request becomes a suggestion row through the feedback door — only on an engine whose account already
    reports to that door with its own credential. A self-hosted engine sends nothing on its own: he is told the
    suggestion button exists instead. True when the row was handed to the door."""
    if not (request or "").strip():
        return False
    try:
        from nucleo.energy import account as cloud_account
        if not cloud_account.is_cloud_account():
            return False
        import asyncio

        from server import feedback_api as _fb
        asyncio.get_running_loop().create_task(_fb._deliver({"message": request.strip()[:1000], "type": "idea"}, None))
        return True
    except Exception as e:  # noqa: BLE001
        _note('suggestion hand-off', e)
        return False
