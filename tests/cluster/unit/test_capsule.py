#
# Tests for the conversation CAPSULE (connectors/meshkore/capsule.py, V2-069 “a single mind”).
# Run: .venv/bin/pytest tests/cluster/unit/test_capsule.py -q
#
# Covers what prevented the forensic failures (re-introduction, infinite loop, lost objective):
#   · phases derived from the relationship state (do not re-introduce oneself during work/probing)
#   · stall detection (pure functions: continue/assertive/silent)
#   · scope-partitioned persistence in memory (sys_kv) without touching the operator's state
#   · composition of the context block (dossier + objective + loops + phase)
#
import pytest

from connectors.meshkore import capsule
from memory import db as memdb


@pytest.fixture
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


# ── phases (pure) ─────────────────────────────────────────────────────────────────────────────────────────────
def test_phase_saludo_first_contact():
    assert capsule.derive_phase({"greeted": False}) == capsule.SALUDO


def test_phase_sondeo_known_no_objective():
    assert capsule.derive_phase({"greeted": True, "objective": ""}) == capsule.SONDEO


def test_phase_trabajo_known_with_objective():
    assert capsule.derive_phase({"greeted": True, "objective": "algoritmo de trading"}) == capsule.TRABAJO


def test_phase_cierre_when_concluded():
    assert capsule.derive_phase({"greeted": True, "objective": "x"}, concluded=True) == capsule.CIERRE


def test_phase_guidance_trabajo_forbids_reintroduction():
    g = capsule.phase_guidance(capsule.TRABAJO).lower()
    assert "no te presentes" in g and "no saludes" in g


# ── atasco (puras) ───────────────────────────────────────────────────────────────────────────────────────────
def test_stall_seguir_when_healthy():
    assert capsule.stall_verdict(repeat_count=0, no_progress=0) == "seguir"
    assert capsule.stall_verdict(repeat_count=1, no_progress=1) == "seguir"


def test_stall_asertivo_at_threshold():
    assert capsule.stall_verdict(repeat_count=2, no_progress=0) == "asertivo"
    assert capsule.stall_verdict(repeat_count=0, no_progress=4) == "asertivo"


def test_stall_callar_when_sustained():
# the peer that repeated "one moment" 1,333 times should fall into 'silent' much sooner, rather than continuing to respond
    assert capsule.stall_verdict(repeat_count=99, no_progress=0) == "callar"
    assert capsule.stall_verdict(repeat_count=0, no_progress=99) == "callar"


def test_norm_collapses_accent_and_emoji_variants():
    # the two spellings of "…one moment" from the real loop reduce to the same key
    a = capsule.norm("Zalo está consultando con su equipo, un momento")
    b = capsule.norm("Zalo esta consultando con su equipo 🧠 un momento")
    assert a == b


# ── scope-partitioned persistence ────────────────────────────────────────────────────────────────────────────
def test_persist_and_load_roundtrip(fresh_db):
    capsule.patch("meshcore", "zalo", objective="algoritmo de trading", greeted=True)
    cap = capsule.load("meshcore", "zalo")
    assert cap["objective"] == "algoritmo de trading"
    assert cap["greeted"] is True


def test_capsules_are_isolated_per_peer(fresh_db):
    capsule.patch("meshcore", "zalo", objective="trading")
    capsule.patch("meshcore", "otro", objective="otra cosa")
    assert capsule.load("meshcore", "zalo")["objective"] == "trading"
    assert capsule.load("meshcore", "otro")["objective"] == "otra cosa"


def test_capsule_does_not_touch_operator_state(fresh_db):
    from memory import api as memory
    before = dict(memory.state())
    capsule.patch("meshcore", "zalo", objective="trading", greeted=True)
    # the operator's ROOT state remains intact (the capsule lives in sys_kv, in a separate scope)
    assert dict(memory.state()) == before


def test_add_open_loop_dedup_and_cap(fresh_db):
    for i in range(12):
        capsule.add_open_loop("meshcore", "zalo", f"pendiente {i}")
    capsule.add_open_loop("meshcore", "zalo", "pendiente 11")   # normalized duplicate → does not grow
    loops = capsule.load("meshcore", "zalo")["open_loops"]
    assert len(loops) == 8            # cap
    assert loops[-1] == "pendiente 11"


# ── context composition ──────────────────────────────────────────────────────────────────────────────────────
def test_compose_includes_objective_and_phase(fresh_db):
    cap = capsule.patch("meshcore", "zalo", objective="algoritmo de trading", greeted=True,
                        phase=capsule.TRABAJO)
    block = capsule.compose("meshcore", "zalo", cap)
    assert "algoritmo de trading" in block
    assert "zalo" in block
    assert "no te presentes" in block.lower()   # the TRABAJO phase guidance is embedded


def test_compose_new_peer_has_no_invented_objective(fresh_db):
    block = capsule.compose("meshcore", "nuevo")
    assert "no te inventes uno" in block.lower()
