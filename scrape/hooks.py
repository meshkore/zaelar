"""scrape/hooks.py — the module's outward calls, as SEAMS the host wires at boot (V2-846; `search/hooks.py`'s pattern).

`scrape/` never imports the turn, the workers or `memory/`. What it needs from the engine it gets through these:

  · `map_fields(instructions, sample) -> dict | None` — the fast model maps a site's listing keys to fields, ONCE per
    site (`mapping.py`). Wired in the engine to the fast model through its usual chain; unset, the shape map is used.
  · `note_source(source, outcome, detail)` — a wall or a refusal goes into the ONE per-source record of the engine
    (CRIT-E17, `nucleo/workers/source_outcomes.py`), the same row the browser and the workers write.
  · `touch()` — a read is real work: it marks the engine's activity clock, so an engine that stops when idle never
    stops with a read in flight (measured 2026-11-04: a Fly Machine stopped for idleness in the middle of a read).

Unset, each is a no-op and the module works alone.
"""
from __future__ import annotations

import json
from typing import Callable

from loguru import logger

model: Callable[[str, str], str | None] | None = None      # (system, user) → the model's text, or None
note: Callable[[str, str, str], None] | None = None          # (source, outcome, detail)
activity: Callable[[], None] | None = None                   # marks the engine's real-activity clock


def map_fields(instructions: str, sample: str) -> dict | None:
    """The model's field map for these sample objects, parsed; None when there is no model or no usable answer."""
    if model is None:
        return None
    try:
        raw = model(instructions, sample) or ""
        start, end = raw.find("{"), raw.rfind("}")
        return json.loads(raw[start:end + 1]) if start >= 0 < end else None
    except Exception as e:  # noqa: BLE001 — a mapping that could not be asked leaves the shape map standing
        logger.info(f"scrape: no model mapping ({type(e).__name__}: {str(e)[:120]})")
        return None


def touch() -> None:
    if activity is None:
        return
    try:
        activity()
    except Exception as e:  # noqa: BLE001 — the clock is the host's; a failed mark never fails a read
        logger.debug(f"scrape: activity not marked ({e!r})")


def note_source(source: str, outcome: str, detail: str = "") -> None:
    if note is None:
        return
    try:
        note(source, outcome, detail)
    except Exception as e:  # noqa: BLE001 — the record is the host's; a failed write never fails a read
        logger.debug(f"scrape: source not noted ({e!r})")
