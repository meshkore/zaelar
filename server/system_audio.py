"""system_audio.py — can the machine itself be heard? (operator request, 2026-09-10)

The ◉ status panel said «Todo bien» while nothing could possibly sound: the OS output volume at zero, or
muted, is invisible to a browser (no web API reads it), and the self-host engine runs ON the operator's own
machine — so the SERVER can ask the OS and the panel can say it. His framing is the contract: *«ese monitor
precisamente es para detectar si el volumen está cero en el ordenador… si yo veo ahí una alerta, ya me doy
por enterado»*.

macOS only for now (the operator's machine; `osascript` ships with the OS). Everything else answers None —
an ABSENT row, never a fake green one: claiming «volume ok» on an OS we did not measure is the exact lie
this module exists to remove. Cached, because /api/status is polled every 15 s and a subprocess per poll is
rude; the cache is short enough that a volume change shows within a minute.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time

_TTL_S = 45.0
_cache: tuple[float, dict | None] | None = None


def _read_macos() -> dict | None:
    """One osascript call answers volume AND mute: `output volume:54, input volume:75, …, output muted:false`."""
    try:
        out = subprocess.run(["osascript", "-e", "get volume settings"],
                             capture_output=True, text=True, timeout=4).stdout
        vol = re.search(r"output volume:(\d+)", out)
        muted = re.search(r"output muted:(\w+)", out)
        if not vol:
            return None
        return {"volume": int(vol.group(1)), "muted": (muted.group(1).lower() == "true") if muted else False}
    except Exception:  # noqa: BLE001 — a broken probe is an absent row, never a crash in /api/status
        return None


def output_status(now: float | None = None) -> dict | None:
    """{"volume": 0-100, "muted": bool} for the OS output device, or None where it cannot be measured."""
    global _cache
    now = time.time() if now is None else now
    if _cache is not None and now - _cache[0] < _TTL_S:
        return _cache[1]
    result = _read_macos() if sys.platform == "darwin" else None
    _cache = (now, result)
    return result


def status_item() -> dict | None:
    """The ready-made /api/status row, or None where the OS was not measured."""
    s = output_status()
    if s is None:
        return None
    if s["muted"]:
        state, detail = "warn", "SILENCIADA en el sistema — actívala para oír a zaelar"
    elif s["volume"] == 0:
        state, detail = "warn", "volumen del sistema a 0 — sube el volumen para oír a zaelar"
    else:
        state, detail = "ok", f"volumen del sistema {s['volume']}%"
    return {"key": "sysaudio", "label": "Salida de audio · máquina", "state": state, "detail": detail}
