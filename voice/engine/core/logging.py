"""Structured logging for debugging voice sessions.

Console lines (human) + a JSONL event log per process (machine): every state
transition, transcript, interruption, metric and error appended one JSON object
per line, so a session can be replayed / grepped after the fact.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

from .config import SETTINGS


def _ts() -> str:
    lt = time.localtime()
    return time.strftime("%Y-%m-%d %H:%M:%S", lt) + f".{int((time.time() % 1) * 1000):03d}"


class JsonlEventLog:
    """Append-only JSONL event sink. One file per process run."""

    def __init__(self, kind: str) -> None:
        SETTINGS.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
        self.path: Path = SETTINGS.log_dir / f"{kind}-{stamp}.jsonl"
        self._fh = self.path.open("a", encoding="utf-8")

    def emit(self, event: str, **fields: Any) -> None:
        record = {"t": _ts(), "mono": round(time.monotonic(), 4), "event": event}
        record.update(fields)
        try:
            self._fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._fh.flush()
        except Exception:  # logging must never crash the pipeline
            pass

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


def setup_console_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s  %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    )
    root.addHandler(handler)
    root.setLevel(level)
    # The still-open "2º fallo de dispatch" (INI-013, 2026-07-07: worker registers fine but LiveKit sometimes never
    # offers it a job for a new room — root cause unconfirmed, needs the actual availability-request → accept →
    # job → entrypoint handshake) can ONLY be root-caused with the SDK's own protocol-level logs, which INFO hides.
    # ZAELAR_LIVEKIT_LOG_LEVEL=DEBUG (env, read at boot) flips this on for the next live reproduction — leave unset
    # in normal operation, this is verbose (WS frames, availability requests) and not meant to run always-on.
    lk_level = os.getenv("ZAELAR_LIVEKIT_LOG_LEVEL", "INFO").upper()
    logging.getLogger("livekit").setLevel(getattr(logging, lk_level, logging.INFO))
