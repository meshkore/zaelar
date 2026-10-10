"""nucleo/workers/rate_retry.py — a TRANSIENT rate limit is waited out, not declared a death (2026-10-10).

Measured 2026-10-10 20:54 (use case `build-workout-tracker-widget__us`): the widget agent's `claude` exited 1 seven
seconds after it started with

    API Error: Request rejected (429) · [1302][Rate limit reached for requests]

— Z.ai's per-minute limit, served through its Anthropic-compatible endpoint. The CLI's own three retries
(`CLAUDE_CODE_MAX_RETRIES=3`, `providers.env_for_worker`) are spent within those seven seconds, and the
generator's provider ladder (`generator._run_agent`) only relays on a cause `providers.note_failure` returns —
which is `None` for a rate limit, on purpose: a transient limit must not put a healthy tier on cooldown. So the
one failure that waiting DOES fix was the one nobody waited for, and the operator was left with «I'll let you
know the moment it's ready» over an errand that had already died.

The rule lives here, in one place, for both runners (the generator and the Brain Worker relay):

  · ONLY `rate`. A credit/quota limit (402, «limit exhausted», a 429 that announces its reset time) does not clear
    in seconds, and neither does a rejected key or a bad request: retrying them burns the operator's wait and,
    for credit, the provider's patience. `failure_class.classify` already orders quota BEFORE rate, and
    `providers.classify_failure` adds the window/reset reading; a text must be `rate` for BOTH to qualify.
  · BOUNDED and SMALL. A voice errand cannot sit behind a minute of backoff: two retries, jittered exponential
    delays, and a hard ceiling on the total wait (`RATE_RETRY_MAX_TOTAL_S`).
  · CANCELLABLE. A stop during the wait is honoured between slices, never after the whole delay.
"""
from __future__ import annotations

import os
import random
import time

from loguru import logger

#: How many EXTRA attempts a rate-limited run gets (the first run is not counted).
RATE_RETRIES = int(os.getenv("RATE_RETRIES", "2"))
#: The first delay, in seconds; each next one doubles it (before jitter).
RATE_RETRY_BASE_S = float(os.getenv("RATE_RETRY_BASE_S", "4"))
#: Ceiling on the TOTAL time spent waiting across all retries of one run.
RATE_RETRY_MAX_TOTAL_S = float(os.getenv("RATE_RETRY_MAX_TOTAL_S", "20"))
#: ±fraction of jitter on every delay, so two workers limited together do not retry in lockstep.
_JITTER = 0.25
_SLICE_S = 0.25


def is_transient(error_text: str) -> bool:
    """True only for a transient rate limit — the one failure that waiting a few seconds fixes."""
    t = str(error_text or "")
    if not t.strip():
        return False
    try:
        from nucleo.failure_class import classify
        from nucleo.workers.providers import classify_failure
    except Exception:  # noqa: BLE001
        return False
    return classify(t) == "rate" and classify_failure(t) in ("rate", "")


def delays(n: int | None = None, *, base: float | None = None, cap_total: float | None = None,
           rng=random.random) -> list[float]:
    """The jittered exponential delays for `n` retries, trimmed so their SUM never exceeds `cap_total`."""
    n = RATE_RETRIES if n is None else max(0, int(n))
    base = RATE_RETRY_BASE_S if base is None else float(base)
    cap_total = RATE_RETRY_MAX_TOTAL_S if cap_total is None else float(cap_total)
    out, total = [], 0.0
    for i in range(n):
        d = base * (2 ** i) * (1.0 + _JITTER * (2.0 * rng() - 1.0))
        d = max(0.0, min(d, cap_total - total))
        if d <= 0.0:
            break
        out.append(round(d, 2))
        total += d
    return out


def _wait(seconds: float, cancelled, sleep) -> bool:
    """Sleep in slices; False as soon as `cancelled()` says so."""
    end = time.monotonic() + seconds
    while True:
        if cancelled():
            return False
        left = end - time.monotonic()
        if left <= 0:
            return True
        sleep(min(_SLICE_S, left))


def ride_out(run_once, first, *, error_of, label: str = "worker", cancelled=lambda: False,
             sleep=time.sleep, waits: list[float] | None = None):
    """Re-run `run_once()` while its result is a transient rate limit, up to the bounded schedule.

    `first` is the result of the run already made; `error_of(result)` returns its error text ("" = success).
    Returns the last result. A cancellation during a wait returns the last result as it was — the caller
    knows its own cancellation and says it."""
    res = first
    schedule = delays() if waits is None else list(waits)
    for i, d in enumerate(schedule, start=1):
        err = error_of(res)
        if not err or not is_transient(err):
            return res
        logger.warning(f"{label}: provider rate-limited → retry {i}/{len(schedule)} in {d:.1f}s "
                       f"({str(err)[:120]})")
        try:
            from voice.observer import emit as _emit
            _emit("task", "⏳ rate limit — waiting it out", role="system", text=str(err)[:160],
                  extra={"attempt": i, "of": len(schedule), "wait_s": d, "who": label})
        except Exception as e:  # noqa: BLE001
            logger.debug(f"{label}: rate-limit emit failed — {type(e).__name__}: {e}")
        if not _wait(d, cancelled, sleep):
            return res
        res = run_once()
    return res


def relaunch_after_rate(rec, relay_cap: int, *, schedule=None) -> bool:
    """A Brain Worker whose session ENDED on a transient rate limit is relaunched ONCE, after one jittered delay,
    on the same ladder the provider relay uses (`relay.relay_out_of_fuel`). Mutates `rec`; never raises.

    Only the raw provider text qualifies (`rec.result_summary` as the CLI wrote it): the widget generator writes
    its own sentence there after waiting out the limit itself, so it is never relaunched a second time here. The
    cap is the relay chain's (`relay_gen`) — a relaunch that is rate-limited again ends as a death, honestly."""
    try:
        if (rec.ok or rec.status == "cancelled" or rec.handoff or rec.provider_down or rec.context_full
                or int(rec.relay_gen or 0) >= int(relay_cap) or not is_transient(rec.result_summary)):
            return False
        wait = (delays(1) or [RATE_RETRY_BASE_S])[0]
        ctx = {"src": "provider_failover", "kind": rec.kind, "trace": rec.trace_id,
               "sheet": str(getattr(rec, "sheet", "") or ""), "surface": str(getattr(rec, "surface", "") or ""),
               "task_uid": str(getattr(rec, "uid", "") or ""),
               "depth": int(rec.depth or 0), "relay_gen": int(rec.relay_gen or 0) + 1}
        goal, tid = rec.goal, rec.task_id

        def _go():
            try:
                from nucleo.flash import escalate as _esc
                _esc.escalate_to_slowbrain(goal, context=ctx)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"worker[{tid}]: rate-limit relaunch failed: {e}")
        if schedule is None:
            import asyncio
            try:
                asyncio.get_running_loop().call_later(wait, _go)
            except RuntimeError:
                import threading
                threading.Timer(wait, _go).start()
        else:
            schedule(wait, _go)
        rec.result_summary = ""          # no delivery: the relaunched worker carries the errand
        rec.ok = False
        rec.handoff = f"proveedor saturado (rate limit) → reintento en {wait:.0f}s"
        logger.warning(f"worker[{tid}]: provider rate-limited → relaunching in {wait:.1f}s")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"worker: rate-limit relaunch skipped: {e}")
        return False
