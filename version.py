#
# version.py — SELLO DE VERSIÓN del motor (V2-074). Para SABER, sin ambigüedad, qué código está corriendo en una
# instancia y qué versión generó cada línea de la observabilidad. Nace de una necesidad real (2026-07-26): tras
# varios reinicios con código nuevo, no había forma de confirmar que la instancia viva y las líneas del timeline
# eran de la versión actualizada.
#
# Expone: una VERSIÓN semántica (se sube a mano en cambios notables) + el SHA corto de git (cambia solo en cada
# commit) + el instante de arranque del proceso. Todo cacheado (el SHA se lee una vez; leerlo son µs después).
#
import os
import subprocess
import time

# Semantic version of the engine — bump it by hand when closing a notable block of changes (latest:
# voice.trace.active() gives observability events an explicit trace pointer instead of relying on a ContextVar
# that LiveKit's sibling tasks structurally can't see (root-caused at the SDK source level); V2-103's memory
# test suite hardening closed the gap that let its 3 write/REM bugs pass unnoticed for weeks; and
# mem_processor's DeepSeek-direct endpoint now actually disables reasoning, matching the finding from V2-102).
VERSION = "3.13"

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE: dict = {}
_STARTED_MS = round(time.time() * 1000)


def sha() -> str:
    """SHA corto de git del árbol que se está ejecutando (cacheado). 'nogit' si no hay repo/git."""
    if "sha" not in _CACHE:
        try:
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_HERE,
                               capture_output=True, text=True, timeout=2)
            _CACHE["sha"] = (r.stdout or "").strip() or "nogit"
        except Exception:
            _CACHE["sha"] = "nogit"
    return _CACHE["sha"]


def short() -> str:
    """Etiqueta compacta para sellar CADA evento de observabilidad: '2.74+a1b2c3d'. Barata (constante en runtime)."""
    if "short" not in _CACHE:
        _CACHE["short"] = f"{VERSION}+{sha()}"
    return _CACHE["short"]


def started_ms() -> int:
    """Epoch ms en que arrancó ESTE proceso (para distinguir instancias/reinicios en la observabilidad)."""
    return _STARTED_MS


def info() -> dict:
    """Detalle para /api/status y el frontend."""
    return {"version": VERSION, "sha": sha(), "short": short(), "started_ms": _STARTED_MS,
            "uptime_s": round((time.time() * 1000 - _STARTED_MS) / 1000)}
