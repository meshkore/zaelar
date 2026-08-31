#
# Tests of the AUTONOMOUS HEARTBEAT (homeostasis, V2-070). Run: .venv/bin/pytest tests/infrastructure/unit/core/test_homeostasis.py -q
#
# DETERMINISTIC guarantee that the layer keeping the machine alive does the right thing WITHOUT requiring an actual
# incident (which is rare): the decisions are testable pure functions + the IN-PROCESS detector + actual rotation on
# disk. Covers the 2026-07-25 failure (degraded LiveKit engine) through its detection and SAFETY logic.
#
import logging
import os
import time

from nucleo import homeostasis as H


# ── 1) degraded-engine detection (pure) ─────────────────────────────────────────────────────────────────────────
def test_livekit_degraded_threshold():
    now = 1000.0
    assert not H.livekit_degraded([now, now], now, window_s=180, threshold=3)      # 2 < 3
    assert H.livekit_degraded([now, now, now], now, window_s=180, threshold=3)     # 3 >= 3


def test_livekit_degraded_window_expires_old_marks():
    now = 1000.0
    old = [now - 500, now - 400, now - 300]   # all outside the 180s window
    assert not H.livekit_degraded(old, now, window_s=180, threshold=3)
    mixed = old + [now, now - 10, now - 20]    # 3 recent entries
    assert H.livekit_degraded(mixed, now, window_s=180, threshold=3)


# ── 2) recycling SAFETY gate (pure) — never cut off a live conversation ─────────────────────────────────────────
def test_safe_to_recycle_voice_on_never():
    now = 1000.0
    assert not H.safe_to_recycle(True, now - 999, now, idle_s=120)   # live voice → never


def test_safe_to_recycle_idle_ok():
    now = 1000.0
    assert H.safe_to_recycle(False, now - 200, now, idle_s=120)      # voice off + 200s idle → safe


def test_safe_to_recycle_recent_activity_blocks():
    now = 1000.0
    assert not H.safe_to_recycle(False, now - 30, now, idle_s=120)   # activity 30s ago → do not touch


# ── 3) capsule eviction (pure) ──────────────────────────────────────────────────────────────────────────────────
def test_capsules_evict_concluded_and_old():
    now = 1_000_000.0
    ttl = 100.0
    items = [
        ("capsule:c:viejo_cerrado", {"phase": "cierre", "updated": now - 200}),   # evict (closed + old)
        ("capsule:c:cerrado_reciente", {"phase": "cierre", "updated": now - 10}),  # keep (fresh)
        ("capsule:c:trabajando", {"phase": "trabajo", "updated": now - 999}),      # keep (active, not closed)
    ]
    out = H.capsules_to_evict(items, now, max_count=100, ttl_s=ttl)
    assert out == ["capsule:c:viejo_cerrado"]


def test_capsules_evict_over_max_drops_oldest():
    now = 1000.0
    items = [(f"capsule:c:p{i}", {"phase": "trabajo", "updated": now - i}) for i in range(5)]
    # p0 is the newest (updated=now), p4 the oldest (updated=now-4). max=3 → 2 too many → the 2 oldest.
    out = H.capsules_to_evict(items, now, max_count=3, ttl_s=1e9)
    assert set(out) == {"capsule:c:p4", "capsule:c:p3"}


def test_capsules_no_evict_under_limits():
    now = 1000.0
    items = [("capsule:c:a", {"phase": "trabajo", "updated": now})]
    assert H.capsules_to_evict(items, now, max_count=100, ttl_s=1e9) == []


# ── 4) log rotation (pure + actual IO) ──────────────────────────────────────────────────────────────────────────
def test_logs_to_rotate_over_cap():
    sizes = [("/x/a.jsonl", 10), ("/x/b.jsonl", 100)]
    assert H.logs_to_rotate(sizes, cap_bytes=50) == ["/x/b.jsonl"]


def test_rotate_log_renames_and_prunes(tmp_path):
    p = tmp_path / "timeline-latest.jsonl"
    p.write_text("dato\n" * 100)
    # pre-existing rotated files (more than are retained) to test pruning
    for i in range(5):
        old = tmp_path / f"timeline-latest.jsonl.2020010{i}-000000"
        old.write_text("x")
        os.utime(old, (1_000 + i, 1_000 + i))   # increasing mtimes → i=4 is the newest
    H._rotate_log(str(p), keep=3)
    assert not p.exists()                                          # the live file was moved
    rotated = [f for f in os.listdir(tmp_path) if f.startswith("timeline-latest.jsonl.")]
    assert len(rotated) == 3                                       # retains exactly `keep`


# ── 5) IN-PROCESS detector (the SDK's logging watcher) ──────────────────────────────────────────────────────────
def _record(msg: str) -> logging.LogRecord:
    return logging.LogRecord("livekit.agents", logging.WARNING, __file__, 1, msg, None, None)


def test_watcher_marks_on_degradation_signal():
    H._marks.clear()
    H._watcher.emit(_record("worker job: wait_pc_connection timed out after 15s"))
    H._watcher.emit(_record("entrypoint did not exit in time"))
    assert len(H._marks) == 2


def test_watcher_ignores_unrelated_logs():
    H._marks.clear()
    H._watcher.emit(_record("participant connected"))
    H._watcher.emit(_record("track subscribed ok"))
    assert H._marks == []


# ── 6) kill switch ──────────────────────────────────────────────────────────────────────────────────────────────
def test_enabled_kill_switch(monkeypatch):
    monkeypatch.setenv("ZAELAR_HOMEOSTASIS", "0")
    assert not H.enabled()
    monkeypatch.setenv("ZAELAR_HOMEOSTASIS", "1")
    assert H.enabled()
