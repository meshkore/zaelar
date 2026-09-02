#
# version.py — ENGINE VERSION SEAL (V2-074). To KNOW, without ambiguity, what code is running in an
# instance and which version generated each line of observability. It arose from a real need (2026-07-26): after
# several restarts with new code, there was no way to confirm that the live instance and the timeline lines
# belonged to the updated version.
#
# Exposes: a semantic VERSION (bumped by hand for notable changes) + the short git SHA (changes only on each
# commit) + the process start time. Everything is cached (the SHA is read once; subsequent reads take µs).
#
import os
import subprocess
import time

# Semantic version of the engine — bump it by hand when closing a notable block of changes.
#
# Latest (3.17): THE IMAGE, AND WHAT IT WAS MISSING. Three things that all shipped without a single red
# light. V2-553 the update channel — a build NUMBER a person can compare and a bar that offers a reload
# only when the FRONTEND changed. V2-554 `config/models.default.json` was being dropped from the cloud
# image by `.dockerignore`, and it did not crash the boot: the error was swallowed by the try/except
# around the «Colmena» block, so four routers silently did not mount and the smoke went green over it.
# And `widgets/instances.py` used `_re` with no `import re as _re` — valid syntax, green suite (the
# working tree had the import, the tagged commit did not), three fail-soft callers, and three shipped
# behaviours quietly gone. All three are now guarded: what git tracks inside a COPY must reach the
# image (7.16), and no module may use a name it lacks at import time (7.30).
#
# Previous: DELIVERY + REACH. Two blocks, both closed the same night.
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
VERSION = "3.17"

_HERE = os.path.dirname(os.path.abspath(__file__))
_CACHE: dict = {}
_STARTED_MS = round(time.time() * 1000)


def sha() -> str:
    """Short git SHA of the tree being executed (cached). 'nogit' if there is no repo/git."""
    if "sha" not in _CACHE:
        try:
            r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_HERE,
                               capture_output=True, text=True, timeout=2)
            _CACHE["sha"] = (r.stdout or "").strip() or "nogit"
        except Exception:
            _CACHE["sha"] = "nogit"
    return _CACHE["sha"]


def short() -> str:
    """Compact label for sealing EVERY observability event: '2.74+a1b2c3d'. Cheap (constant at runtime)."""
    if "short" not in _CACHE:
        _CACHE["short"] = f"{VERSION}+{sha()}"
    return _CACHE["short"]


def started_ms() -> int:
    """Epoch ms when THIS process started (to distinguish instances/restarts in observability)."""
    return _STARTED_MS


def info() -> dict:
    """Details for /api/status and the frontend."""
    return {"version": VERSION, "sha": sha(), "short": short(), "started_ms": _STARTED_MS,
            "uptime_s": round((time.time() * 1000 - _STARTED_MS) / 1000)}
