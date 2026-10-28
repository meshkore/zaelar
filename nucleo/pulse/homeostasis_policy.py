"""nucleo/pulse/homeostasis_policy.py — the PURE decisions of the heartbeat (degraded? safe to recycle? what to
evict or rotate?), testable without server or IO. Public face: `nucleo.pulse.homeostasis`."""
from __future__ import annotations

import os

# The thresholds, env-overridable; `homeostasis` re-exports them (it imports this module, never the reverse).
_LK_WINDOW_S = float(os.getenv("HOMEOSTASIS_LK_WINDOW_S", "180"))    # window for counting engine marks
_LK_THRESHOLD = int(os.getenv("HOMEOSTASIS_LK_THRESHOLD", "3"))      # marks in the window = degraded
_IDLE_S = float(os.getenv("HOMEOSTASIS_IDLE_S", "120"))             # idle = no timeline write for N s
_LOG_CAP_BYTES = int(os.getenv("HOMEOSTASIS_LOG_CAP_BYTES", str(64 * 1024 * 1024)))  # 64 MB
_CAP_MAX = int(os.getenv("HOMEOSTASIS_CAPSULE_MAX", "200"))         # cap on live capsules
_CAP_TTL_S = float(os.getenv("HOMEOSTASIS_CAPSULE_TTL_S", str(30 * 24 * 3600)))  # concluded+old → evict (30d)


def livekit_degraded(marks: list[float], now: float, *, window_s: float = _LK_WINDOW_S,
                     threshold: int = _LK_THRESHOLD) -> bool:
    """Degraded when >= `threshold` marks fall inside the last window."""
    recent = [t for t in marks if now - t <= window_s]
    return len(recent) >= threshold


def safe_to_recycle(voice_on: bool, last_activity_ts: float, now: float, *, idle_s: float = _IDLE_S) -> bool:
    """Recycle only with no live voice and `idle_s` of channel silence, so it never cuts a conversation."""
    if voice_on:
        return False
    return (now - last_activity_ts) >= idle_s


def capsules_to_evict(items: list[tuple[str, dict]], now: float, *, max_count: int = _CAP_MAX,
                      ttl_s: float = _CAP_TTL_S) -> list[str]:
    """Keys to evict: concluded (phase cierre) and older than ttl; then the oldest by `updated` down to the cap."""
    stale = set()
    for key, cap in items:
        phase = (cap.get("phase") or "").lower()
        updated = float(cap.get("updated") or 0)
        if phase == "cierre" and (now - updated) >= ttl_s:
            stale.add(key)
    survivors = [(k, c) for k, c in items if k not in stale]
    over = len(survivors) - max_count
    if over > 0:
        survivors.sort(key=lambda kc: float(kc[1].get("updated") or 0))   # oldest first
        stale.update(k for k, _ in survivors[:over])
    # keep input order for a stable output
    return [k for k, _ in items if k in stale]


def logs_to_rotate(sizes: list[tuple[str, int]], *, cap_bytes: int = _LOG_CAP_BYTES) -> list[str]:
    """Logs over the size cap."""
    return [path for path, size in sizes if size > cap_bytes]
