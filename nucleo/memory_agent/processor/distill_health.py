"""The HEART's health: the failure streak, the ◉, and who served the last pill.

A failure here is never a debug line (the heart was once down two days in silence): a failure streak past
`ALERT_AFTER` turns the ◉ amber, recovery clears it. Metering lives with the call (`distill.record_usage`).
"""
from __future__ import annotations

import os
import time

from loguru import logger

from nucleo.memory_agent.processor import distill_config as cfg

ALERT_AFTER = max(1, int(os.getenv("MEM_PROCESSOR_ALERT_AFTER", "3")))
_fail_streak = 0
_last_error: str = ""
_last_ok_ts: float = 0.0
_alerted = False
served_rung: tuple[str, str] | None = None     # (base_url, model) of the rung that served the LAST distillation


def status() -> dict:
    """`model`/`url` are the TITULAR (what is configured); `serving_*` are who answered last and `relayed` says
    whether they differ. Separate keys on purpose: a caller after the configuration must not read the relay."""
    srv, m, u = served_rung, cfg.model(), cfg.url()
    return {"model": m, "url": u, "fail_streak": _fail_streak,
            "last_error": _last_error, "last_ok_ts": _last_ok_ts, "degraded": _alerted,
            "serving_model": (srv[1] if srv else m),
            "serving_url": (srv[0] if srv else u),
            "relayed": bool(srv and (srv[1] != m or srv[0] != u))}


def mark_ok() -> None:
    global _fail_streak, _last_ok_ts, _alerted
    _last_ok_ts = time.time()
    if _alerted:
        # The ◉ is the place for «something is wrong»; no top banner (V2-066, the operator asked it gone).
        try:
            from voice import health_state
            health_state.clear("memory")
        except Exception:
            pass
        logger.warning(f"mem_processor: RECUPERADO ({cfg.model()}) tras {_fail_streak} fallos")
    _fail_streak = 0
    _alerted = False


def mark_fail(err: str) -> None:
    global _fail_streak, _last_error, _alerted
    _fail_streak += 1
    _last_error = err
    logger.warning(f"mem_processor: fallo {_fail_streak}/{ALERT_AFTER} ({cfg.model()} @ {cfg.url()}): "
                   f"{err[:160]} → heurística")
    if _fail_streak >= ALERT_AFTER and not _alerted:
        _alerted = True
        try:
            from voice import health_state
            health_state.record("memory", "outage",
                                f"{_fail_streak} fallos ({cfg.model()} @ {cfg.url()}): {err[:160]} — heurística")
        except Exception:
            pass

