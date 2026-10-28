"""The pulse's shared signals: what it says to a worker, how it emits, and how it delivers a notice."""
from __future__ import annotations

import os

from loguru import logger

_STUCK_KEY = "worker_stuck:"          # V2-776 D2 — retractable key of the «it went quiet» notice
#: Key for the RETRACTABLE notice «it has been N minutes, should I stop it?» — one per task (V2-353).
_TIMEOUT_KEY = "worker-timeout:"
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
    """Publish a loop signal through the Nervous System (best-effort, loop-agnostic)."""
    try:
        import bus
        bus.emit_sync(topic, payload or {})
    except Exception:
        pass


async def _default_deliver(title: str, text: str, key: str = "") -> None:
    """Deliver through the existing proactive rails (voice + UI). Best-effort.

    `key` (V2-353) travels to the brain's mailbox so a note asserting something about LIVE state can be
    RETRACTED if it stops being true before delivery — see `voice.brain_notes.push`.
    """
    try:
        from voice import proactive
        await proactive.notify(title or "zaelar", text, key=key)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"loop deliver failed: {e}")
