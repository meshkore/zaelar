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

# Semantic version of the engine — bump it by hand when closing a notable block of changes.
#
# Latest: DELIVERY + REACH. Two blocks, both closed the same night.
#
#   DELIVERY — V2-475 the guarantees now speak the operator's language (they were mute in English and spoke
#   Spanish into English replies), V2-478 the backstop's gate is no longer LENGTH but whether the turn NAMES
#   what the sheet holds, V2-479 twelve rows travel instead of five, V2-480 the worker's door into the
#   scheduler normalizes like the other two, V2-481 a cold start no longer shows raw i18n keys.
#
#   REACH — V2-486 the «ask the mesh first» step reached only the BROWSER prompt, and a hotel that is SEARCHED
#   (rather than booked) is routed to the generic worker, which never named the bridge: the network was built,
#   verified live, and consulted zero times in 399 worker reports. V2-487 an agent answering 400 with the
#   field it needs HAS answered — that was flattened into «the network did not reply», which sends a Chromium
#   at Booking with the answer one field away; measured live, ten real New York hotels in 0.4 s. V2-488 the
#   research composer asked a model that CANNOT stop reasoning to stop reasoning, and a 400 gives no relay
#   tier, so every directed search silently degraded to a blind one. V2-489 the round now says whether the
#   worker asked the network at all. V2-490 a critical health limit is repeated LAST and phrased as a check on
#   what is about to be said — measurement still pending, and its initiative says so.
VERSION = "3.16"

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
