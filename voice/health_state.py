#
# PROCESS-LEVEL HEALTH STATE — a tiny, brain-agnostic record of the LAST provider failure per external service,
# so the ⓘ status panel can turn red when something is actually wrong (no credit/quota, bad key, outage) instead
# of the operator discovering it only when zaelar goes mute.
#
# WHY reactive: the paid APIs we use (AIMLAPI for the LLM, Deepgram for STT/TTS) expose no balance endpoint, so we
# can't poll a number ahead of time. We learn a service is unhealthy the moment a call fails — the voice error
# guard (voice/llm_health.py) already classifies those failures; here we just REMEMBER the latest one (kind +
# short text + when) and clear it on the next success. /api/status reads this snapshot.
#
# Keep it minimal and dependency-free: one dict, guarded by nothing (single-process, event-loop + worker threads
# only do coarse whole-dict writes, which are atomic enough for a status readout).
#
import time

# service -> {"kind": "credit|auth|outage", "text": <short>, "ts": <epoch>}  ·  absent = healthy
_errors: dict[str, dict] = {}

TTL = 600.0   # an error older than this is treated as stale (assume recovered until proven otherwise)


def record(service: str, kind: str, text: str = "") -> None:
    """Remember that `service` (e.g. 'llm', 'stt', 'tts', 'cluster') just failed with `kind`."""
    _errors[service] = {"kind": kind, "text": (text or "")[:200], "ts": time.time()}


def clear(service: str) -> None:
    """A call to `service` succeeded → it's healthy again."""
    _errors.pop(service, None)


def get(service: str) -> dict | None:
    """Return the fresh error for `service`, or None if healthy / stale."""
    e = _errors.get(service)
    if not e:
        return None
    if time.time() - e.get("ts", 0) > TTL:
        _errors.pop(service, None)
        return None
    return e


def snapshot() -> dict:
    """All currently-fresh errors, keyed by service (for /api/status)."""
    return {svc: e for svc in list(_errors) if (e := get(svc))}
