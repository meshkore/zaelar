"""The pulse's shared signals: what it says to a worker, how it emits, and how it delivers a notice."""
from __future__ import annotations

import os

from loguru import logger

_STUCK_KEY = "worker_stuck:"          # V2-776 D2 — retractable key of the «it went quiet» notice
# V2-227 scope B2: how many seconds between heartbeats for a live task. Few, because the failure it fixes is the
# SILENCE —seven minutes of a motionless screen— and no less, because a PERSON reads the rail: one heartbeat per
# second is not information, it is timestamped noise. Adjustable through the environment so it can be measured.
_BEAT_SECS = float(os.getenv("ZAELAR_TASK_BEAT_SECS", "15") or 15)
# V2-776 D2 — a worker that has not reported ITSELF (`hbnote`) for this long is told to. The stream shows it
# is alive; only its own report says WHERE it is, and «encourage it in the prompt» measured as optional.
_REPORT_SECS = float(os.getenv("ZAELAR_WORKER_REPORT_SECS", "90") or 90)
#: Backends that can run `hbnote`. The widget generator is a one-shot CLI with file tools only: it cannot
#: report, and nudging it would be a message nobody reads.
_REPORTING_BACKENDS = frozenset({"claude_code", "codex", "grok_build"})
#: What the pulse injects. Worker-facing prompt text, in the language of the worker prompts.
REPORT_DEMAND = ("INFORME DE ESTADO OBLIGATORIO: llevas un rato sin decir dónde estás. Ahora mismo, antes de "
                 "tu siguiente paso, ejecuta `python -m nucleo.cli.report phase \"<qué estás haciendo, en una "
                 "frase>\"` y, si declaraste un plan, `python -m nucleo.cli.report progress \"<nota>\" --done "
                 "<pasos hechos>`. Luego sigue.")


def _observe(label: str, text: str = "", **extra) -> None:
    """V2-776 D5 — a pulse decision about a worker, on the OBSERVER timeline (family `task` → the
    «Brain Workers» column of the ◷ observability viewer). The bus signal above is for in-process listeners; the
    observability viewer reads this one."""
    try:
        from voice.observer import emit
        emit("task", label, role="system", text=text[:200], extra=extra)
    except Exception:  # noqa: BLE001
        pass


def _emit(topic: str, payload: dict | None = None) -> None:
    """Publish a loop signal through the Nervous System (best-effort, loop-agnostic) — and mirror it on the observer
    timeline (kind `pulse`), where both surfaces read it. Neither half can take the loop down."""
    try:
        import bus
        bus.emit_sync(topic, payload or {})
    except Exception:
        pass
    try:
        _mirror(topic, payload or {})
    except Exception as e:  # noqa: BLE001 — a record of the beat never stops the beat
        logger.debug(f"pulse: {topic} not mirrored on the timeline ({e!r})")


# ── the beat on the observer timeline (capture gaps, 2026-11-06) ───────────────────────────────────────────────
#: A cycle that took at least this long did real work (awaited a supervisor, fired a job) and is recorded on its own.
TICK_MIN_MS = int(os.getenv("ZAELAR_PULSE_TICK_MIN_MS", "250") or 250)
#: Every this many cycles a `beat` sums the period: how many ticks, their mean and max — the quiet seconds, counted.
BEAT_TICKS = int(os.getenv("ZAELAR_PULSE_BEAT_TICKS", "60") or 60)
#: What of a signal's payload travels as the row's text, bounded: his words (a reminder's prompt, a spark).
_TEXT_KEYS = ("prompt", "text")
_TEXT_MAX = 200
_period = {"ticks": 0, "ms": 0, "max": 0, "slow": 0}


def _mirror(topic: str, payload: dict) -> None:
    """One `loop.<signal>` → one observer row `pulse · <signal>` with the payload's scalars as fields and its words as a
    bounded text. The tick is the exception: recorded alone only when slow, otherwise summed into the next `beat`."""
    if not topic.startswith("loop."):
        return
    name = topic[5:]
    if name == "tick":
        _tick(payload)
        return
    text = ""
    extra = {}
    for k, v in payload.items():
        if k in _TEXT_KEYS:
            text = text or str(v or "")[:_TEXT_MAX]
        elif isinstance(v, (str, int, float, bool)) and v not in ("", None):
            extra[k] = v if not isinstance(v, str) else v[:120]
    from voice.observer import emit
    emit("pulse", name, text=text, role="system", extra=extra)


def _tick(payload: dict) -> None:
    try:
        ms = int(payload.get("ms") or 0)
    except (TypeError, ValueError):
        ms = 0
    p = _period
    p["ticks"] += 1
    p["ms"] += ms
    p["max"] = max(p["max"], ms)
    from voice.observer import emit
    if ms >= TICK_MIN_MS:
        p["slow"] += 1
        emit("pulse", "tick", role="system", extra={"n": payload.get("n"), "ms": ms})
    if p["ticks"] >= BEAT_TICKS:
        emit("pulse", "beat", role="system",
             extra={"n": payload.get("n"), "ticks": p["ticks"], "avg_ms": round(p["ms"] / p["ticks"]),
                    "max_ms": p["max"], "slow": p["slow"]})
        p.update(ticks=0, ms=0, max=0, slow=0)


async def _default_deliver(title: str, text: str, key: str = "", task_id: str = "", ask_id: str = "") -> None:
    """Deliver through the out-of-turn mouth (`notices.notify`, V2-851 F2): a line of a task names its `task_id`, a
    notice its `key`. Best-effort.

    `key` (V2-353) is the notice's identity at the out-of-turn door (the brain's notes mailbox it also reached went in
    V2-851 F5).
    """
    try:
        from nucleo.pulse import notices
        await notices.notify(title or "zaelar", text, key=key, task_id=task_id, ask_id=ask_id, kind="info")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"loop deliver failed: {e}")
