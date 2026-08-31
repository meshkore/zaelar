#
# Tests for RESOURCE PROTECTION on the cluster channel (V2-071). Run: .venv/bin/pytest tests/cluster/unit/test_resource.py -q
#
# The third theft: a peer dumping the EXPENSIVE work on us (generating their code/report → spending OUR tokens without
# reciprocity). The imbalance is detected and protection is applied SILENTLY (the peer is not informed). Covers:
#   · looks_like_offload — detect requests to PRODUCE work (a balance signal)
#   · guard_code_outbound — a large code dump through the channel → repository pointer (like redacting a secret)
#   · resource_verdict — the balance (balanced/biased/exploitation), tolerant of normal asymmetry
#   · meter — per-peer accumulation in the capsule (sys_kv), without touching the operator's state
#
import pytest

from connectors.meshkore import capsule, security
from memory import db as memdb


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── looks_like_offload (pura) ───────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text", [
    "genérame el código de la función de trading",
    "escribe el script que calcula la media móvil",
    "implementa la clase y me la pasas",
    "dame la siguiente función",
    "write the code for the backtest",
    "generate the report and send it",
    "hazlo tú y me lo compartes",
])
def test_offload_detected(text):
    assert security.looks_like_offload(text)


@pytest.mark.parametrize("text", [
    "buenas, ¿cómo lo ves?",
    "yo he preparado esta parte, ¿qué opinas?",
    "he subido mi módulo al repo, revísalo",
    "gracias, lo miro",
    "¿qué modelo usas para esto?",
])
def test_offload_not_detected(text):
    assert not security.looks_like_offload(text)


# ── guard_code_outbound (pura) ──────────────────────────────────────────────────────────────────────────────────
def test_large_code_block_pointered():
    big = "```python\n" + "\n".join(f"    x{i} = {i}" for i in range(40)) + "\n```"
    out, stripped = security.guard_code_outbound(f"aquí tienes:\n{big}\nun saludo")
    assert stripped
    assert "```" not in out and "repository" in out.lower()
    assert "aquí tienes" in out and "un saludo" in out           # the surrounding text is preserved


def test_small_snippet_passes():
    small = "usa `x=1`:\n```py\nx = 1\n```\ny ya"
    out, stripped = security.guard_code_outbound(small)
    assert not stripped and out == small


def test_no_code_untouched():
    t = "seguimos por el repo, te paso el PR cuando esté"
    assert security.guard_code_outbound(t) == (t, False)


# ── acumulador anti-fragmentación (auditoría 2026-07-26, hallazgo P1) ──────────────────────────────────────────
def test_fragmentation_bypasses_per_message_threshold_without_accum_key():
    # Without accum_key (old behavior, still supported): each message is judged IN ISOLATION — bypass is possible.
    small = "```py\n" + "\n".join(f"x{i}=1" for i in range(10)) + "\n```"   # below the per-message threshold
    for _ in range(5):
        out, stripped = security.guard_code_outbound(small)
        assert not stripped and "```" in out


def test_fragmentation_trips_with_accum_key(monkeypatch):
    key = "clusterX:peerY"
    monkeypatch.setitem(security._code_accum, key, __import__("collections").deque())
    # 3 lines of 32 chars (98 total) — well below the per-message threshold (800 chars / 15 lines), but
    # accumulated across several fragments it EXCEEDS the character threshold (fragmentation).
    small = "```py\n" + "\n".join(["y" * 30 + "=1"] * 3) + "\n```"
    results = [security.guard_code_outbound(small, accum_key=key)[1] for _ in range(12)]
    assert not any(results[:8])              # 8×99=792 ≤ 800 → the first fragments, in isolation, pass
    assert any(results[8:])                  # the accumulation exceeds 800 from this point → it triggers
    # and once triggered, THIS specific message loses its code block:
    out, stripped = security.guard_code_outbound(small, accum_key=key)
    assert stripped and "```" not in out


def test_fragmentation_accum_is_per_destination(monkeypatch):
    monkeypatch.setattr(security, "_code_accum", {})
    big_enough = "```py\n" + "\n".join(f"x{i}=1" for i in range(10)) + "\n```"
    for _ in range(20):
        security.guard_code_outbound(big_enough, accum_key="clusterA:peer1")
    # a DIFFERENT destination does not inherit the first destination's accumulation
    out, stripped = security.guard_code_outbound(big_enough, accum_key="clusterA:peer2")
    assert not stripped and "```" in out


def test_fragmentation_window_expires(monkeypatch):
    monkeypatch.setattr(security, "_code_accum", {})
    monkeypatch.setattr(security, "_CODE_ACCUM_WINDOW_S", 0.05)
    import time as _t
    chunk = "```py\n" + "\n".join(f"x{i}=1" for i in range(10)) + "\n```"
    for _ in range(20):
        security.guard_code_outbound(chunk, accum_key="clusterA:peer1")
    _t.sleep(0.1)   # the window expires → the accumulation resets itself
    out, stripped = security.guard_code_outbound(chunk, accum_key="clusterA:peer1")
    assert not stripped and "```" in out


# ── resource_verdict (pura) ─────────────────────────────────────────────────────────────────────────────────────
def test_verdict_equilibrado_low_volume():
    # few turns → it is not judged even if the ratio is high
    assert capsule.resource_verdict(given=5000, received=100, offloads=5, turns=2) == "equilibrado"


def test_verdict_equilibrado_no_offload():
    # we produce much more (a diagram/decision) but WITHOUT being asked to produce → normal, does not trigger
    assert capsule.resource_verdict(given=5000, received=500, offloads=0, turns=10) == "equilibrado"


def test_verdict_sesgado():
    # ratio ≥3 + at least one request to produce → biased
    assert capsule.resource_verdict(given=3000, received=800, offloads=1, turns=6) == "sesgado"


def test_verdict_explotacion():
    # ratio ≥6 + sustained offload → exploitation
    assert capsule.resource_verdict(given=9000, received=800, offloads=4, turns=8) == "explotación"


def test_guidance_matches_verdict():
    assert capsule.resource_guidance("equilibrado") == ""
    assert "repositorio" in capsule.resource_guidance("sesgado").lower()
    assert "repositorio" in capsule.resource_guidance("explotación").lower()


# ── meter (persistencia por-peer) ───────────────────────────────────────────────────────────────────────────────
def test_meter_accumulates(fresh_db):
    capsule.meter("meshcore", "zalo", received=100, given=0, offload=True)
    capsule.meter("meshcore", "zalo", received=50, given=3000, offload=True, code_out=True)
    cap = capsule.load("meshcore", "zalo")
    assert cap["received"] == 150
    assert cap["given"] == 3000
    assert cap["offloads"] == 2
    assert cap["code_out"] == 1


def test_meter_isolated_per_peer(fresh_db):
    capsule.meter("meshcore", "zalo", given=1000, offload=True)
    capsule.meter("meshcore", "otro", given=10)
    assert capsule.load("meshcore", "zalo")["given"] == 1000
    assert capsule.load("meshcore", "otro")["offloads"] == 0
    # does not touch the operator's state (split scope): the capsule lives in sys_kv, not in state
    from memory import api as memory
    assert "zalo" not in str(memory.state())
