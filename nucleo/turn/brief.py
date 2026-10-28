"""The turn's ONE Jev call: every question a turn needs, declared as DATA and asked once (V2-726 F1/A2, refactor2710-07).

Each question is one entry of `QUESTIONS` — `{key, asked_when, question}` — and the brief, the readers and the tests derive
from that table: there is no second list of what the turn asks. `asked_when(ctx)` says whether this turn needs it (a stop
question only while an errand runs, a redo only when there is something to redo); `question(ctx)` builds its
`{instructions, criteria}` from what is DECLARED (manifest actions of what is open, the request-type list…), never free
text. A question is finished when it is READ (`nucleo/turn/verdicts.py`): nothing here executes anything.

Why one call: Jev's cost is the round trip, not the questions (one question ~800 ms, a hundred ~1 041 ms, measured
2026-09-20). Why post-model questions only: the prompt is built 3 ms after admission and a verdict lands at ~785 ms, so
only what is decided AFTER the model can read a brief fired at admission (the cover filler is the one exception: it is
chosen after the brief lands). It is fired at the ADMITTED sentence — after echo suppression and the accumulator — so the
verdicts judge the same words the model reads. Nobody waits: a brief in flight, failed, disabled or unsure reads as the
caller's own fallback. And a verdict about a card is re-validated when consumed (`owner_still_open`): the brief
enumerates what was open at fire time; two seconds later a card may have closed.
"""
from __future__ import annotations

from nucleo.turn import brief_turn as _bt
from nucleo.turn.brief_turn import (  # noqa: F401 — re-export: which turn a brief belongs to
    PREFIRED_TTL_S, judged_text, of_this_turn, owner_still_open, remember_for_the_turn, stamp, verdict_before_the_turn)
from nucleo.turn.brief_screen import (  # noqa: F401 — re-export: the screen questions and their caps
    CATALOG_INSTRUCTIONS, MAX_CATALOG_CANDIDATES, MAX_DESC_CHARS, MAX_OPEN_CARDS, NAMES_KEY, TARGET_INSTRUCTIONS,
    _base_of, _card_label, _possible_now, catalog_question, names_elsewhere, names_question, target_question)

ESCALATE_KEY = "escalate_or_inline"
CANVAS_KEY = "canvas"
TARGET_KEY = "screen_action"
REQUEST_KEY = "request_type"
WORDS_KEY = "wants_words"
CATALOG_KEY = "catalog_widget"

#: Does he expect to be TOLD something in words? Not `request_type`: «find me five days and tell me the dates» is an
#: ORDER that owes an answer, «go back to the list» an order that owes none (demo pass 2026-09-28, R3 and M1).
WORDS_INSTRUCTIONS = ("Beyond anything done or shown on screen, does the operator expect to be TOLD something in "
                      "words in this turn?")
WORDS_CRITERIA = {
    "tell": "he asks to be told something: a fact, a figure, dates, a price, how something is going, an answer",
    "act": "he only asks for something to be done, opened, shown, played, closed or changed — no answer in words "
           "is owed beyond acknowledging it",
}


def escalate_question(*, running_goals: list | None = None, has_workers: bool = False,
                      ask_pending: bool = False) -> dict:
    """The escalate pair. The state facts travel in THIS question's instructions (a brief has one shared state and
    per-question instructions); `has_workers`/`ask_pending` are read by `ask_for_turn` (A2: they were never passed,
    and «answer the worker» is the shape that must not become a second worker)."""
    from nucleo.flash import escalation_guard as _eg
    goals = [str(g)[:120] for g in (running_goals or []) if str(g or "").strip()][:3]
    facts = ("Goals already in flight: " + ("; ".join(goals) if goals else "none")
             + f". Workers active now: {'yes' if has_workers else 'no'}."
             + f" A worker is waiting for the operator's answer: {'yes' if ask_pending else 'no'}.")
    return {"instructions": f"{_eg.ESCALATE_INSTRUCTIONS} {facts}", "criteria": dict(_eg.ESCALATE_CHOICE)}


def request_question(last_reply: str = "") -> dict:
    """What kind of turn this is. The previous reply rides in THIS question: it is what keeps a curt «enduro» that
    answers our question from being read as an order (V2-716)."""
    from nucleo import jev as _jev
    instructions = _jev._RT_INSTRUCTIONS
    lr = (last_reply or "").strip()
    if lr:
        instructions += f" [Our previous reply: {lr[:200]}]"
    return {"instructions": instructions, "criteria": dict(_jev.REQUEST_TYPES)}


# ── the questions, as data ────────────────────────────────────────────────────────────────────────────────────────
# `ctx` = {operator_text, open_ids, running_goals, has_workers, ask_pending, last_reply}. Each `question` builder lives
# with the mechanism that reads its answer (its owner), so the wording and the reader cannot drift apart.

def _canvas(_ctx):
    from nucleo.flash import show_target as _st
    return {"instructions": _st.CANVAS_INSTRUCTIONS, "criteria": dict(_st.CANVAS_VERBS)}


def _build(_ctx):
    from nucleo.flash import build_decision as _bd
    return _bd.build_question()


def _surface(_ctx):
    from nucleo import surfaces as _sf
    return _sf.question()


def _search(_ctx):
    from search import route as _route
    return _route.question()


def _redo(_ctx):
    from nucleo.flash import redo_decision as _redo_d
    return _redo_d.question()


def _end_state(ctx):
    from nucleo.circuit import spec as _spec
    return _spec.end_state_question(ctx.get("open_ids"))


def _stop(ctx):
    from nucleo.request import stop as _stop_d
    return _stop_d.question(ctx.get("last_reply") or "")


def _gap(ctx):
    from nucleo.flash import capability_gap as _gap_d
    return _gap_d.question(ctx.get("open_ids"))


def _key(module: str, name: str) -> str:
    import importlib
    return str(getattr(importlib.import_module(module), name))


#: Every question a turn may ask: `(key, asked_when, question)`. A key given as `(module, name)` is the owner's own
#: constant, read when the table is used, so the owner stays the one place that names it.
QUESTIONS = (
    (CANVAS_KEY, None, _canvas),
    (REQUEST_KEY, None, lambda c: request_question(c.get("last_reply") or "")),
    (("nucleo.flash.build_decision", "BUILD_KEY"), None, _build),
    (ESCALATE_KEY, None, lambda c: escalate_question(running_goals=c.get("running_goals"),
                                                     has_workers=bool(c.get("has_workers")),
                                                     ask_pending=bool(c.get("ask_pending")))),
    (WORDS_KEY, None, lambda c: {"instructions": WORDS_INSTRUCTIONS, "criteria": dict(WORDS_CRITERIA)}),
    (("nucleo.surfaces", "SURFACE_KEY"), None, _surface),
    (("search.route", "SEARCH_KEY"), None, _search),
    (("nucleo.flash.redo_decision", "REDO_KEY"), None, _redo),                 # None when nothing is behind us
    (("nucleo.circuit.spec", "END_KEY"), None, _end_state),
    (("nucleo.request.stop", "KEY"), lambda c: bool(c.get("has_workers")), _stop),   # only while an errand runs
    (("nucleo.flash.capability_gap", "KEY"), None, _gap),
    (TARGET_KEY, lambda c: bool(c.get("open_ids")), lambda c: target_question(c.get("open_ids"))),
    (CATALOG_KEY, lambda c: not target_question(c.get("open_ids")), lambda _c: catalog_question()),
    (NAMES_KEY, lambda c: bool(c.get("open_ids")), lambda c: names_question(c.get("open_ids"))),
)


def build(operator_text: str, *, open_ids=None, running_goals=None, has_workers: bool = False,
          ask_pending: bool = False, last_reply: str = "") -> dict:
    """The questions this turn will need after the model answers, from `QUESTIONS`. Empty dict = nothing to ask.

    `screen_action` and `catalog_widget` are never both asked: with cards open the ACTION disambiguates (0.94 vs 0.26
    measured); with nothing open the catalogue is the useful question one step earlier."""
    if not (operator_text or "").strip():
        return {}
    ctx = {"operator_text": operator_text, "open_ids": open_ids, "running_goals": running_goals,
           "has_workers": has_workers, "ask_pending": ask_pending, "last_reply": last_reply}
    qs: dict[str, dict] = {}
    for key, asked_when, question in QUESTIONS:
        try:
            if asked_when is not None and not asked_when(ctx):
                continue
            q = question(ctx)
            if q:
                qs[_key(*key) if isinstance(key, tuple) else key] = q
        except Exception as e:  # noqa: BLE001 — one question that cannot be built never costs the others
            from loguru import logger
            logger.debug(f"brief: question {key!r} not built — {e!r}")
    return qs


def keys() -> list[str]:
    """Every key the brief may carry, in table order — what the tests and the readers enumerate."""
    return [_key(*k) if isinstance(k, tuple) else k for k, _w, _q in QUESTIONS]


def _worker_state() -> tuple[bool, bool]:
    """(workers active, a worker is waiting for an answer). Unknown reads as «no», the escalating answer."""
    try:
        from nucleo import dispatch as _dispatch, worker_api as _wapi
        return bool(_dispatch.has_active()), bool(_wapi.has_pending_ask())
    except Exception:  # noqa: BLE001
        return False, False


def ask_for_turn(operator_text: str, *, running_goals=None, last_reply: str = "", turn_id=None):
    """Fire the brief for a live voice turn, reading the screen and worker state itself. `operator_text` must be the
    ADMITTED sentence. Never raises: no state reads as nothing open."""
    if (pre := _bt.prefired(operator_text)) is not None:
        return pre
    try:
        from memory import api as _memapi
        open_ids = list((_memapi.state() or {}).get("open_widgets") or [])
    except Exception:  # noqa: BLE001
        open_ids = []
    has_workers, ask_pending = _worker_state()
    return ask(operator_text, open_ids=open_ids, running_goals=running_goals,
               has_workers=has_workers, ask_pending=ask_pending, last_reply=last_reply, turn_id=turn_id)


def ask(operator_text: str, *, turn_id=None, **kw):
    """Fire the turn's brief. Returns a handle for `read`, or None when there is nothing to ask (empty turn, Jev off,
    no key). Never raises."""
    try:
        from nucleo import jev as _jev
        if not _jev.enabled():
            return None
        questions = build(operator_text, **kw)
        if not questions:
            return None
        handle = _jev.ask_many(operator_text.strip(), questions, name="jev-turn-brief", question_id="turn-brief")
        handle = stamp(handle, turn_id=turn_id, open_ids=kw.get("open_ids"))
        if isinstance(handle, dict):
            handle["judged"] = operator_text.strip()     # V2-820 T-06: the sentence the verdicts are about
        return handle
    except Exception:  # noqa: BLE001 — a classifier may never break a turn
        return None


def read(handle, key: str, fallback, *, min_confidence: float | None = None):
    """One verdict out of the brief — the asymmetric read's door (`nucleo/turn/verdicts.read`), kept under this name
    for the readers that spell it `turn_brief.read`."""
    from nucleo.turn import verdicts
    return verdicts.read(handle, key, fallback, min_confidence=min_confidence)
