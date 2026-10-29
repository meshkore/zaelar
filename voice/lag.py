"""voice/lag.py — the voice measures its own lag and acts (V2-831 T-30).

On the operator's cloud host the deaf stretches lined up with errands running: the VAD fell behind real time and the
job executor stopped answering its pings, and nothing in the engine READ either — they were log lines. Two declared
signals now feed one reader:
  · the voice loop's own lag: a probe on the session's event loop measures how late its own sleeps wake (`watch`);
  · the SDK's measured delays (VAD inference behind real time, the executor's ping), read from the log RECORD's
    `delay` field, never from its words (`_SdkDelays`).
Over the declared bound (`voice_lag_s` in `config/resources.default.json`, a rule with this reader) it says so: an
event, ONE spoken notice in his language per cooldown, and load shed through the worker envelope (T-27).
"""
from __future__ import annotations

import asyncio
import logging
import time

from loguru import logger

_PERIOD_S = 0.5
_COOLDOWN_S = 60.0
_state = {"last_act": -1e9, "loops": set(), "worst": 0.0, "episode": False}


def bound_s() -> float:
    from nucleo.workers import envelope
    return float(envelope.policy().get("voice_lag_s", 0.5))


def note(lag_s: float, source: str) -> bool:
    """One lag reading. Over the bound it acts — event and shed once per cooldown, the spoken notice once per EPISODE
    (said again only after the lag has recovered and come back)."""
    _state["worst"] = max(_state["worst"], lag_s)
    now = time.monotonic()
    if lag_s < bound_s():
        _state["episode"] = False        # recovered: the next episode may be said again
        return False
    if now - _state["last_act"] < _COOLDOWN_S:
        return False
    _state["last_act"] = now
    first, _state["episode"] = not _state["episode"], True
    try:
        from voice.observer import emit
        emit("alert", "La voz va con retraso — pauso el trabajo de fondo.", role="system",
             extra={"cat": "voice", "kind_diag": "voice_lag", "lag_s": round(lag_s, 2), "source": source})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"lag: event not emitted: {e!r}")
    try:
        from nucleo.workers import envelope
        envelope.shed(_COOLDOWN_S)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"lag: load not shed: {e!r}")
    try:
        from i18n import langs
        from voice import proactive
        line = str(getattr(langs.current_language(), "voice_lag_notice", "") or "")
        if line and first:
            asyncio.get_running_loop().create_task(proactive.notify("zaelar", line, about="voice_lag"))
    except Exception as e:  # noqa: BLE001 — no running loop (a thread) or no notifier: the event still stands
        logger.debug(f"lag: notice not spoken: {e!r}")
    return True


async def _probe(period_s: float = _PERIOD_S) -> None:
    loop = asyncio.get_running_loop()
    while True:
        t0 = loop.time()
        await asyncio.sleep(period_s)
        note(max(0.0, loop.time() - t0 - period_s), "voice_loop")


def watch() -> None:
    """Measure the CURRENT event loop (the voice session's) for as long as it runs. Idempotent per loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as e:
        logger.debug(f"lag: no running loop to measure ({e})")
        return
    if id(loop) in _state["loops"]:
        return
    _state["loops"].add(id(loop))
    loop.create_task(_probe(), name="voice-lag-probe")
    _SdkDelays.install()


class _SdkDelays(logging.Handler):
    """The SDK's own measured delays, read from the record's `delay` field (VAD: seconds; executor ping: ms)."""
    _installed = False

    @classmethod
    def install(cls) -> None:
        if not cls._installed:
            logging.getLogger("livekit").addHandler(cls(level=logging.WARNING))
            cls._installed = True

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D401
        delay = getattr(record, "delay", None)
        if not isinstance(delay, (int, float)):
            return
        src = str(getattr(record, "filename", "") or "")
        note(float(delay) / (1000.0 if "executor" in src or "proc" in src else 1.0), src or "livekit")
