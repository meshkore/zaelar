#
# PROCESS-LEVEL HEALTH STATE — a tiny, brain-agnostic record of the LAST provider failure per external service,
# so the ⓘ status panel can turn red when something is actually wrong (no credit/quota, bad key, outage) instead
# of the operator discovering it only when zaelar goes mute.
#
# WHY reactive: the paid APIs we use (the LLM provider, Deepgram for STT/TTS) may expose no balance endpoint, so we
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
    _errors[service] = {"kind": kind, "text": (text or "")[:200], "ts": time.time(), "cls": _classify(text)}


def _classify(text: str) -> str:
    try:
        from nucleo.failure_class import classify
        return classify(text or "")
    except Exception:  # noqa: BLE001
        return "ours"


def revalidate_network(probe) -> int:
    """A `network`-class failure is a fact about the CONNECTION, not the provider (2026-10-20: a Wi-Fi switch left
    the memory card red for 10 minutes after the network was back, because only a later memory call could clear
    it). When `probe()` says the network answers, every such record is dropped. Blocking — call in a thread.
    Returns how many were dropped; never runs the probe when there is nothing to revalidate."""
    stale = [svc for svc, e in list(_errors.items()) if e.get("cls") == "network"]
    if not stale or not probe():
        return 0
    for svc in stale:
        _errors.pop(svc, None)
    return len(stale)


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
