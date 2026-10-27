"""voice/attention_lines.py — every line the attention gate ADMITS, what its judge said, what it may renew and
what it licenses (V2-812 T-03).

Kept apart from `voice/attention.py` (which imports the public names back) because that file was at its size
ceiling; the state it reads — the window anchor — stays there, and this module reaches it through the module, so a
test that resets `attention` resets it too (`attention.reset` calls `reset` here).
"""
from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from loguru import logger

from voice.attention_judge import _as_judgement

if TYPE_CHECKING:  # `voice.attention` imports this module back: the name is for the annotation only
    from voice.attention import Verdict

# ── V2-812 T-03 · THE LINE IS STILL JUDGED INSIDE THE WINDOW ───────────────────────────────────────────────
# Measured in a car (session e52cd845, «always», 30 s window): 68 of 68 lines admitted, about half of them talk
# between the passengers, a dozen answered, five side effects started from lines that were not orders — «Eso
# es.» resumed a failed booking from the day before. Two holes, both in this module: inside the window nothing
# was judged (V2-534), and every handled line — and every word of the reply to it — renewed the window, so
# while anybody in the car spoke every 30 s the conversation could not die.
#
# The window still admits WITHOUT waiting for the judge: blocking on it would put ~0.9 s (p50, measured on
# those 51 lines) in front of every reply, and the judge alone is not trusted to DROP a line inside a
# conversation — on the same session it read «estamos viendo la portada de Shakira, pero no suena» as room
# talk. What changes is what a line admitted that way can do. It is judged BESIDE the turn (`open_line`), and:
#   · a line judged NOT addressed does not renew the window — neither its admission nor the agent's reply to
#     it (`note_directed`, `note_bot_speech`); the anchor goes back to where it was before the line;
#   · a side effect started from a line that is not a clear request to the agent asks first — that is
#     `licence()`, read by the one consent rule (`nucleo/consent.decide`) and by the one door a worker starts
#     through (`nucleo/dispatch_confirm.unlicensed_gate`).
# A wake word, a typed line and a push-to-talk line are addressed by construction and license nothing new:
# their licence stays unknown (None), which every reader treats as today's behaviour.

_LINES: dict = {}            # trace id → line record (insertion-ordered, bounded)
_LINES_MAX = 64
_LATEST = {"key": ""}        # the most recent line — what the agent's own mouth is answering
_JUDGE_TASKS: set = set()    # strong refs: a fire-and-forget task may be collected mid-flight otherwise


def _current_trace() -> str:
    from voice import trace as _trace
    return _trace.current() or ""


def _line(trace: str = "") -> dict | None:
    key = trace or _current_trace()
    return _LINES.get(key) if key else None


def open_line(verdict: "Verdict", *, text: str, context: str = "", trace: str = "",
              now: float | None = None) -> dict:
    """Register the line the gate just ADMITTED, keyed by its turn's trace, and judge it beside the turn when
    nobody judged it on the way in. Called by the gate's caller (`attention_turn.judge`) BEFORE it renews the
    window, so the anchor the line found is the one a negative verdict restores. Never raises, never blocks."""
    from voice import attention as _a
    now = time.time() if now is None else now
    key = trace or _current_trace() or f"line:{now:.6f}"
    prev = _LINES.get(key)   # a fragment that ADOPTED this trace keeps the anchor the line first found
    line = {"key": key, "text": (text or "")[:300], "at": now,
            "anchor": prev["anchor"] if prev else _a._state["last_directed"],
            "recent": list(prev["recent"]) if prev else list(_a._state["recent_directed"]), "reason": verdict.reason,
            "addressed": None, "request": None, "pending": False, "granted": False}
    if verdict.by_act or _a.typed_line(text, now=now):
        line["addressed"] = True                       # addressed by an act of his; licence stays unknown
    elif verdict.judged:
        line["addressed"], line["request"] = bool(verdict.directed), verdict.request
    elif _a.mode() == "always" and verdict.directed and verdict.reason != "always":
        # admitted with nobody judging it (the window, no frame, the unanswered streak) — judged beside the turn;
        # a bare `always` admission is the judge having FAILED, and asking it again would only fail again
        line["pending"] = True
    _LINES.pop(key, None)
    _LINES[key] = line
    while len(_LINES) > _LINES_MAX:
        _LINES.pop(next(iter(_LINES)))
    _LATEST["key"] = key
    if line["pending"]:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            line["pending"] = False                    # no loop to judge on: unknown, today's behaviour
            return line
        task = loop.create_task(_judge_line(line, context))
        _JUDGE_TASKS.add(task)
        task.add_done_callback(_JUDGE_TASKS.discard)
    return line


async def _judge_line(line: dict, context: str) -> None:
    from voice import attention as _a
    try:
        directed, request = _as_judgement(await _a._directed_judge(line["text"], context))
    except Exception as e:  # noqa: BLE001 — the judge failing must leave the line as it was admitted
        logger.warning(f"attention._judge_line: judge failed ({str(e)[:160]}) — the line keeps its admission")
        directed, request = None, None
    settle_line(line["key"], directed=directed, request=request)


def settle_line(key: str, *, directed: bool | None, request: bool | None, now: float | None = None) -> None:
    """The verdict on an admitted line arrived. A judge that failed (`directed=None`) leaves it as admitted —
    addressed, licence unknown — because a broken judge must never take a turn away (fail-open, as the gate)."""
    line = _LINES.get(key)
    if not line:
        return
    line["pending"] = False
    line["addressed"] = True if directed is None else bool(directed)
    line["request"] = None if directed is None else (bool(request) if request is not None else None)
    if line["addressed"]:
        return
    # Not addressed: the window goes back to the anchor the line found — but only while this is still the
    # latest line. A newer one re-anchored on its own account, and rolling back would eat ITS window.
    from voice import attention as _a
    rolled = False
    if _LATEST["key"] == key:
        _a._state["last_directed"] = line["anchor"]
        _a._state["recent_directed"] = list(line["recent"])
        rolled = True
    try:
        from voice.observer import emit
        emit("ambient", "🙉 en ventana — no iba dirigida (no renueva la ventana)", text=line["text"][:160],
             role="user", extra={"reason": "window_unaddressed", "rolled_back": rolled, "trace": key,
                                 "window_s": _a.window_s(), "window_open": _a.window_warm()})
    except Exception as e:  # noqa: BLE001 — the observer is optional; the rollback above already happened
        logger.debug(f"attention_lines: could not emit the unaddressed line ({e})")


def licence(trace: str = "") -> bool | None:
    """May a side effect start from this line WITHOUT asking? True: judged addressed and a clear request, or
    licensed by his yes (`grant_line`). False: judged and NOT both. None: unknown — no line for this trace, not
    judged (a wake word, a typed line, smart mode) or still being judged — and every reader keeps today's path."""
    line = _line(trace)
    if not line:
        return None
    if line["granted"]:
        return True
    if line["pending"] or line["addressed"] is None:
        return None
    if line["addressed"] is False:
        return False
    return None if line["request"] is None else bool(line["request"])


async def wait_licence(trace: str = "", timeout_s: float = 2.5) -> bool | None:
    """`licence()`, waiting up to `timeout_s` for a verdict still on its way — for an async door (the worker
    gate) that runs seconds after the turn. Polls, so it works from any loop or thread."""
    deadline = time.monotonic() + max(0.0, timeout_s)
    while True:
        line = _line(trace)
        if not line or not line["pending"] or time.monotonic() >= deadline:
            return licence(trace)
        await asyncio.sleep(0.05)


def grant_line(trace: str = "") -> None:
    """His explicit YES to the question an unlicensed line raised licenses that line from now on — the worker
    it starts, and that worker's own later acts, carry the trace of the line that asked."""
    line = _line(trace)
    if line:
        line["granted"] = True


def renewal_refused() -> bool:
    """`note_directed` from a line judged NOT addressed renews nothing (V2-812 T-03). Read from the CALLER's
    trace: a write from another context (a typed turn, a wake-word spot) is not this line's reply."""
    key = _current_trace()
    line = _LINES.get(key) if key else None
    return bool(line) and line["addressed"] is False and not line["granted"]


def latest_unaddressed() -> bool:
    """Is the line the agent's mouth is answering right now one judged NOT addressed? Read by the falling edge of
    its speech, which runs in a task that carries no trace (`attention.note_bot_speech`)."""
    line = _LINES.get(_LATEST["key"]) if _LATEST["key"] else None
    return bool(line) and line["addressed"] is False and not line["granted"]


def reset() -> None:
    _LINES.clear()
    _LATEST["key"] = ""
