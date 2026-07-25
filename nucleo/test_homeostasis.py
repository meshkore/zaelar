#
# Tests del LATIDO AUTÓNOMO (homeostasis, V2-070). Run: .venv/bin/pytest nucleo/test_homeostasis.py -q
#
# Garantía DETERMINISTA de que la capa que mantiene la máquina viva hace lo correcto SIN necesidad de un incidente
# real (que es raro): las decisiones son funciones puras testeables + el detector IN-PROCESS + la rotación real en
# disco. Cubre el fallo del 2026-07-25 (motor LiveKit degradado) por su lógica de detección y de SEGURIDAD.
#
import logging
import os
import time

from nucleo import homeostasis as H


# ── 1) detección del motor degradado (pura) ─────────────────────────────────────────────────────────────────────
def test_livekit_degraded_threshold():
    now = 1000.0
    assert not H.livekit_degraded([now, now], now, window_s=180, threshold=3)      # 2 < 3
    assert H.livekit_degraded([now, now, now], now, window_s=180, threshold=3)     # 3 >= 3


def test_livekit_degraded_window_expires_old_marks():
    now = 1000.0
    old = [now - 500, now - 400, now - 300]   # todas fuera de la ventana de 180s
    assert not H.livekit_degraded(old, now, window_s=180, threshold=3)
    mixed = old + [now, now - 10, now - 20]    # 3 recientes
    assert H.livekit_degraded(mixed, now, window_s=180, threshold=3)


# ── 2) puerta de SEGURIDAD del reciclado (pura) — nunca cortar una conversación viva ────────────────────────────
def test_safe_to_recycle_voice_on_never():
    now = 1000.0
    assert not H.safe_to_recycle(True, now - 999, now, idle_s=120)   # voz viva → jamás


def test_safe_to_recycle_idle_ok():
    now = 1000.0
    assert H.safe_to_recycle(False, now - 200, now, idle_s=120)      # voz off + 200s inactivo → seguro


def test_safe_to_recycle_recent_activity_blocks():
    now = 1000.0
    assert not H.safe_to_recycle(False, now - 30, now, idle_s=120)   # actividad hace 30s → no tocar


# ── 3) eviction de cápsulas (pura) ──────────────────────────────────────────────────────────────────────────────
def test_capsules_evict_concluded_and_old():
    now = 1_000_000.0
    ttl = 100.0
    items = [
        ("capsule:c:viejo_cerrado", {"phase": "cierre", "updated": now - 200}),   # evict (cierre + viejo)
        ("capsule:c:cerrado_reciente", {"phase": "cierre", "updated": now - 10}),  # keep (fresco)
        ("capsule:c:trabajando", {"phase": "trabajo", "updated": now - 999}),      # keep (activo, no cierre)
    ]
    out = H.capsules_to_evict(items, now, max_count=100, ttl_s=ttl)
    assert out == ["capsule:c:viejo_cerrado"]


def test_capsules_evict_over_max_drops_oldest():
    now = 1000.0
    items = [(f"capsule:c:p{i}", {"phase": "trabajo", "updated": now - i}) for i in range(5)]
    # p0 es el más nuevo (updated=now), p4 el más viejo (updated=now-4). max=3 → sobran 2 → los 2 más viejos.
    out = H.capsules_to_evict(items, now, max_count=3, ttl_s=1e9)
    assert set(out) == {"capsule:c:p4", "capsule:c:p3"}


def test_capsules_no_evict_under_limits():
    now = 1000.0
    items = [("capsule:c:a", {"phase": "trabajo", "updated": now})]
    assert H.capsules_to_evict(items, now, max_count=100, ttl_s=1e9) == []


# ── 4) rotación de logs (pura + IO real) ────────────────────────────────────────────────────────────────────────
def test_logs_to_rotate_over_cap():
    sizes = [("/x/a.jsonl", 10), ("/x/b.jsonl", 100)]
    assert H.logs_to_rotate(sizes, cap_bytes=50) == ["/x/b.jsonl"]


def test_rotate_log_renames_and_prunes(tmp_path):
    p = tmp_path / "timeline-latest.jsonl"
    p.write_text("dato\n" * 100)
    # pre-existentes rotados (más de los que se conservan) para probar la poda
    for i in range(5):
        old = tmp_path / f"timeline-latest.jsonl.2020010{i}-000000"
        old.write_text("x")
        os.utime(old, (1_000 + i, 1_000 + i))   # mtimes crecientes → el i=4 es el más nuevo
    H._rotate_log(str(p), keep=3)
    assert not p.exists()                                          # el vivo se movió
    rotated = [f for f in os.listdir(tmp_path) if f.startswith("timeline-latest.jsonl.")]
    assert len(rotated) == 3                                       # conserva exactamente `keep`


# ── 5) detector IN-PROCESS (el watcher de logging del SDK) ──────────────────────────────────────────────────────
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


# ── 6) kill-switch ──────────────────────────────────────────────────────────────────────────────────────────────
def test_enabled_kill_switch(monkeypatch):
    monkeypatch.setenv("ZAELAR_HOMEOSTASIS", "0")
    assert not H.enabled()
    monkeypatch.setenv("ZAELAR_HOMEOSTASIS", "1")
    assert H.enabled()
