"""nucleo/workers/quota_wait.py — the worker chain ASLEEP: say it, park the errand, resume it at the reset.

Measured on the use-case rounds of 2026-10-11 (14:14 onwards, z.ai coding plan out of quota and DeepSeek
answering 402): with every tier in cooldown the dispatcher already refused to spawn (V2-314), and yet

  · the turn that escalated came back mute and OUR holding line said «Still on it; I'll let you know as soon
    as I have it» / «Sigue en marcha» — about an errand that was refused before it was born (seven rounds,
    `weekend-motor-events__us` 19:30, `search-rent-apartment__es` 20:19, `search-buy-surfboard__us` 20:11…);
  · «avísame cuando se reabra» got «Done.» / «Te avisaré justo a las 21:11» with `scheduled_jobs` EMPTY: the
    reset hour was KNOWN (the cooldown store has it) and nothing was set to act on it.

So the three halves live here, in one place both channels read:

  · `asleep_line()` — what a holding/mute backstop says instead of claiming work while the chain sleeps;
  · `park()` — a refused or quota-killed errand becomes a durable scheduled job at the reset time (the board
    shows it, `scheduled_jobs` counts it), and its summary says so — a promise with a job behind it;
  · `fire()` — the loop's hook when that job comes due: the quota is back → say so and relaunch the errand;
    still asleep → park once more, or tell the truth with no promise.

Fail-open everywhere: a broken read here means «not asleep», which is the behaviour before this module.
"""
from __future__ import annotations

import re
import time
from types import SimpleNamespace

from loguru import logger

#: How long a turn's own asleep sentence counts as «already said» for the dispatcher's note (one turn).
SAID_WINDOW_S = 90.0
#: How many times one errand is parked per process — a reset hour that keeps lying must not loop forever.
MAX_PARKS = 2
#: The scheduled job fires this long after the reset instant, so the cooldown has really lapsed.
FIRE_MARGIN_S = 60.0

_SAID = {"at": 0.0}
_PARKS: dict[str, int] = {}
_QUOTA_WORD_RE = re.compile(r"\b(cuota|quota)\b", re.I)


def _lang():
    from i18n import langs as _lg
    return _lg.current_language()


def asleep_until() -> float:
    """Epoch at which the worker chain wakes, or 0.0 when a tier is available (or it cannot be read)."""
    try:
        from nucleo.workers import providers as _prov
        return float(_prov.exhausted_until() or 0.0)
    except Exception as e:  # noqa: BLE001 — fail-open: unreadable means «not asleep», the old behaviour
        logger.debug(f"quota_wait: chain state unreadable ({type(e).__name__})")
        return 0.0


def hour(until: float) -> str:
    return time.strftime("%H:%M", time.localtime(until))


def asleep_line(window=None, lang=None) -> str:
    """The sentence a backstop says while the chain sleeps, or "" when work can start. Never the same one twice
    in a row (the judge marked the word-for-word repeat), and it stamps itself so the dispatcher's note for the
    same refusal does not say it a second time."""
    until = asleep_until()
    if not until:
        return ""
    try:
        lang = lang or _lang()
        first = lang.worker_chain_asleep.format(hour=hour(until))
        again = lang.worker_chain_asleep_again.format(hour=hour(until))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"quota_wait: no asleep wording ({type(e).__name__})")
        return ""
    said = [str((m or {}).get("content") or "").strip() for m in (window or [])
            if (m or {}).get("role") == "assistant"]
    _SAID["at"] = time.time()
    return again if (said and said[-1] == first) else first


def said_recently(now: float | None = None) -> bool:
    return ((now or time.time()) - _SAID["at"]) <= SAID_WINDOW_S


def _key(goal: str) -> str:
    return " ".join(str(goal or "").lower().split())[:160]


def _parked_jobs() -> list[dict]:
    try:
        from nucleo.pulse import scheduler as _sched
        return _sched.pending_carrying("resume_errand")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"quota_wait: journal unreadable ({type(e).__name__})")
        return []


def is_parked(goal: str) -> bool:
    k = _key(goal)
    return bool(k) and any(_key(e["detail"]["resume_errand"]) == k for e in _parked_jobs())


def park(goal: str, context: dict | None = None) -> float:
    """Schedule the errand's relaunch at the chain's reset. Returns the reset epoch when the errand is (or
    already was) parked, 0.0 when it could not be — chain awake, no goal, cap reached, or a write failure."""
    goal = str(goal or "").strip()
    until = asleep_until()
    if not goal or not until:
        return 0.0
    if is_parked(goal):
        return until
    k = _key(goal)
    if _PARKS.get(k, 0) >= MAX_PARKS:
        return 0.0
    try:
        from nucleo.pulse import scheduler as _sched
        ctx = {f: str((context or {}).get(f) or "") for f in ("kind", "sheet", "surface", "task_uid")}
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(until + FIRE_MARGIN_S))
        made = _sched.create("", when, name=_lang().worker_chain_job_name.format(goal=goal[:60]))
        if not made.get("ok"):
            return 0.0
        _sched.annotate(made["id"], resume_errand=goal, resume_ctx=ctx)
        _PARKS[k] = _PARKS.get(k, 0) + 1
        logger.info(f"quota_wait: «{goal[:70]}» parked until {hour(until)} (job {made['id']})")
        return until
    except Exception as e:  # noqa: BLE001 — a failed park is the old ending, never a crash
        logger.warning(f"quota_wait: could not park «{goal[:60]}»: {e}")
        return 0.0


def parked_summary(goal: str, context: dict | None, fallback: str) -> str:
    """The ending of an errand the chain refused or killed: parked → the sentence that promises the resume
    (backed by the job), otherwise `fallback` unchanged."""
    until = park(goal, context)
    if not until:
        return fallback
    try:
        return _lang().worker_chain_parked.format(hour=hour(until))
    except Exception:  # noqa: BLE001
        return fallback


async def tell(rec, deliver, *, settle_s: float = 1.5) -> None:
    """Deliver a refused errand's ending, shortened when the turn itself has just said the asleep sentence —
    one fact, said once. Waits `settle_s` so the turn that escalated gets to speak (and stamp) first."""
    import asyncio
    try:
        await asyncio.sleep(settle_s)
        until = asleep_until()
        if until and said_recently() and is_parked(getattr(rec, "goal", "") or ""):
            rec = SimpleNamespace(result_summary=_lang().worker_chain_parked_short.format(hour=hour(until)))
    except Exception as e:  # noqa: BLE001
        logger.debug(f"quota_wait: tell kept the full ending ({type(e).__name__})")
    await deliver(rec)


def takes(detail: dict) -> bool:
    return bool((detail or {}).get("resume_errand"))


async def fire(detail: dict, deliver) -> None:
    """The parked job came due. Quota back → say it and relaunch the SAME errand; still asleep → park again
    (bounded by `MAX_PARKS`) or say the plain asleep sentence, which promises nothing."""
    goal = str((detail or {}).get("resume_errand") or "").strip()
    ctx = dict((detail or {}).get("resume_ctx") or {})
    if not goal:
        return
    if asleep_until():
        if not park(goal, ctx):
            line = asleep_line()
            if line:
                await deliver("zaelar", line)
        return
    await deliver("zaelar", _lang().worker_chain_resumed.format(goal=goal[:70]))
    try:
        from nucleo.flash import escalate as _esc
        _esc.escalate_to_slowbrain(goal, context={**{k: v for k, v in ctx.items() if v}, "src": "quota_resume"})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"quota_wait: relaunch of «{goal[:60]}» failed: {e}")


def forget(which: str = "") -> int:
    """Cancel parked errands — all of them for ""/«todo», else those sharing a content word with `which`. A
    stop he ordered also stops what was waiting for the quota. Returns how many."""
    q = {w for w in re.findall(r"\w{4,}", str(which or "").lower())}
    bulk = not str(which or "").strip() or bool(q & {"todo", "todos", "todas", "everything"})
    n = 0
    try:
        from nucleo.pulse import scheduler as _sched
        for e in _parked_jobs():
            words = set(re.findall(r"\w{4,}", _key(e["detail"]["resume_errand"])))
            if bulk or (q & words):
                n += int(bool(_sched.cancel(str(e["id"]))))
    except Exception as e:  # noqa: BLE001 — the stop itself already ran; a parked job left is on the board
        logger.warning(f"quota_wait: could not forget parked errands: {e}")
    return n
