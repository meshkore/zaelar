"""The latency relay ceiling lifted the cooldown of a provider with NO QUOTA (V2-275).

Measured in `search-secondhand-monitor__es` (2026-08-24 00:56), by reading the round's observability. In the
SAME process, with 260 seconds between them:

    +36.1 s  🔌 cluster brain: «z.ai» (Z.AI GLM) with no quota until 25 Aug 01:39 → relay to «aimlapi»
    +300.3 s 🔌 end of the latency relay: «z.ai» returns (ceiling of 40 turns on «aimlapi»)

`pick()` exhausts the turn ceiling of a LATENCY relay and gives the turn back to the owner «even if it is still
slow» — its own comment says so, so that was always the intent. What was missing was the ability to
say it: `CooldownStore` stored a number and nothing else, and `lift()` deleted the cooldown regardless of its
reason. Thus the latency relay ceiling undid a 24-hour penalty for lack of QUOTA and
sent the next turn to a provider we knew would answer with 429.

Two mechanisms in the same module writing a number and reading it as though it meant only one thing. This is
V2-252 in reverse: there, the cooldown fell on a HEALTHY provider; here, it was removed from a
BROKEN one.

And the ceiling did not have a single test — that is why it survived. These cover both directions, because «never
lift» fixes this case and reintroduces the problem the ceiling exists to prevent: remaining indefinitely on a
more expensive tier.
"""
import time

import pytest

from nucleo import provider_health as ph
from nucleo.flash import provider_chain as pc


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    fresh = pc.CooldownStore(pc._KV)
    fresh._loaded = True                              # without touching real memory
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(pc, "_store", fresh)
    pc._relay_turns.clear()
    for _var in ("Z_AI_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "AIMLAPI_KEY", "XAI_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(_var, raising=False)
    yield
    pc._relay_turns.clear()


def _two_tiers(monkeypatch):
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": [
        {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"]},
        {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "env": ["AIMLAPI_KEY"]},
    ]} if k == "cluster" else {})
    monkeypatch.setenv("Z_AI_API_KEY", "z")
    monkeypatch.setenv("AIMLAPI_KEY", "a")


def _burn_the_relay_budget():
    """Leaves the relay tier with its turn budget exhausted, as after a long conversation."""
    pc._relay_turns["aimlapi"] = pc._RELAY_TURN_BUDGET


# ── the measured defect ──────────────────────────────────────────────────────────────────────────────────
def test_el_techo_NO_resucita_a_un_titular_sin_cuota(monkeypatch):
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)   # no weekly quota, as in the round
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "aimlapi", "le devolvió el turno al proveedor que no tiene cuota"
    assert pc._store.available("z.ai") is False, "el cooldown de SALUD se borró para resolver una latencia"


def test_y_no_se_queda_en_bucle_reintentando_el_techo(monkeypatch):
    """Sin reponer el contador, cada `pick` volvería a entrar en la rama y a emitir el mismo aviso."""
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)
    _burn_the_relay_budget()
    for _ in range(3):
        assert pc.pick()["name"] == "aimlapi"
    assert pc._relay_turns.get("aimlapi", 0) < pc._RELAY_TURN_BUDGET


# ── and the opposite direction, which is what the ceiling exists to do ──────────────────────────────────
def test_pero_SI_lo_resucita_cuando_el_castigo_era_por_LENTITUD(monkeypatch):
    """If this breaks, the fix above leaves the agent stuck on a more expensive tier forever."""
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + pc._SLOW_COOLDOWN_S, ph.REASON_LATENCY)
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "z.ai"
    assert pc._store.available("z.ai") is True


def test_un_titular_lento_Y_sin_cuota_esta_sin_cuota(monkeypatch):
    """The order in which the two penalties arrive must not decide which one prevails."""
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + pc._SLOW_COOLDOWN_S, ph.REASON_LATENCY)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "aimlapi"


def test_y_al_reves_un_castigo_de_salud_no_se_degrada_a_latencia(monkeypatch):
    _two_tiers(monkeypatch)
    pc._store.set("z.ai", time.time() + 86400, ph.REASON_HEALTH)
    pc._store.set("z.ai", time.time() + pc._SLOW_COOLDOWN_S, ph.REASON_LATENCY)
    assert pc._store.why("z.ai") == ph.REASON_HEALTH
    _burn_the_relay_budget()
    assert pc.pick()["name"] == "aimlapi"


# ── the reason is stored and survives, and OLD data is read on the safe side ──────────────────────────────────
def test_los_setters_reales_declaran_su_motivo(monkeypatch):
    """Without this, the default supplies the reason and the fix depends on nobody forgetting to pass it."""
    _two_tiers(monkeypatch)
    reset = time.strftime("%Y-%m-%d", time.localtime(time.time() + 2 * 86400))
    pc.note_failure(f"429 — [1310][Weekly/Monthly Limit Exhausted. Your limit will reset at {reset} 00:00:00]",
                    {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert pc._store.why("z.ai") == ph.REASON_HEALTH

    fresh = pc.CooldownStore(pc._KV)
    fresh._loaded = True
    monkeypatch.setattr(fresh, "_save", lambda: None)
    monkeypatch.setattr(pc, "_store", fresh)
    tier = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"}
    for _ in range(pc._SLOW_STREAK):
        pc.note_slow({"cause": "pre_token", "ttft_ms": 9000}, role=pc.ROLE_CLUSTER, tier=tier)
    assert pc._store.why("z.ai") == ph.REASON_LATENCY, pc._store.why("z.ai")


def test_una_entrada_VIEJA_sin_motivo_se_lee_como_SALUD():
    """What is on disk NOW is `{name: epoch}`. Reading it as latency would be precisely the measured defect.

    A cooldown that cannot be classified is treated as the side that cannot be lifted: hammering a
    broken provider costs the turn, while staying on the relay costs a few cents.
    """
    st = ph.CooldownStore("t:legacy")
    st._loaded = True
    st._save = lambda: None
    saved = {"z.ai": time.time() + 3600}
    st._loaded = False
    st._cooldown, st._why = {}, {}
    import memory.api as memapi
    _real = memapi.kv_get
    memapi.kv_get = lambda k: saved if k == "t:legacy" else None
    try:
        assert st.why("z.ai") == ph.REASON_HEALTH
    finally:
        memapi.kv_get = _real
    st.lift("z.ai", only=ph.REASON_LATENCY)
    assert st.available("z.ai") is False
