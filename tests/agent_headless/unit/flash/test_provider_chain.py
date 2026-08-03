"""Cadena de proveedores del CEREBRO DE CLUSTER + relevo automático (2026-08-03).

Hermano de tests/agent_headless/unit/workers/test_provider_failover.py: mismo incidente-clase (un 429 de Z.AI sin
relevo), pero del lado del turno de cluster (`connectors/meshkore/brain.py` → `nucleo.flash.cluster.respond` →
`FastClient`), no del CLI de los brain workers. Antes de esto el tier se fijaba UNA VEZ al arrancar el server y el
heartbeat repetía la MISMA llamada rota en bucle — "cluster brain turn failed: 429" una y otra vez, sin relevo y
sin que el panel dijera nada.
"""
import time

import pytest

from nucleo.flash import provider_chain as pc

REAL_429_EXHAUSTED = ("429 Too Many Requests — {\"error\":{\"message\":"
                      "\"[1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-08-04 00:00:00]\"}}")
BARE_429 = "429 Too Many Requests"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(pc, "_cooldown", {})
    monkeypatch.setattr(pc, "_loaded", True)          # sin tocar la memoria real
    monkeypatch.setattr(pc, "_save", lambda: None)
    for _var in ("Z_AI_API_KEY", "LLM_API_KEY", "LLM_BASE_URL", "AIMLAPI_KEY", "XAI_API_KEY", "GROQ_API_KEY",
                 "MESHKORE_MISSION_MODEL", "ASSISTANT_LLM_MODEL", "LLM_MODEL", "MESHKORE_MISSION_MODEL_ZAI"):
        monkeypatch.delenv(_var, raising=False)
    yield


def _cfg(monkeypatch, providers=None):
    import config.v2 as v2
    monkeypatch.setattr(v2, "get", lambda k: {"providers": providers or []} if k == "cluster" else {})


# ── zero-config: la cadena por defecto usa las credenciales presentes, en el MISMO orden que antes ──────────
def test_default_chain_prefers_zai_then_aimlapi_then_xai_then_groq(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    monkeypatch.setenv("XAI_API_KEY", "k3")
    monkeypatch.setenv("GROQ_API_KEY", "k4")
    assert [t["name"] for t in pc.chain()] == ["z.ai", "aimlapi", "xai", "groq"]


def test_a_tier_without_credentials_is_not_offered(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert [t["name"] for t in pc.chain()] == ["z.ai"]


def test_explicit_llm_override_wins_over_zai(monkeypatch):
    """Un LLM_BASE_URL/LLM_API_KEY explícito seguía ganando a Z.AI antes de esto (el operador pinchó un endpoint a
    mano) — se preserva reordenando (aimlapi primero), no descartando Z.AI de la cadena."""
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("LLM_API_KEY", "k2")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.aimlapi.com/v1")
    assert [t["name"] for t in pc.chain()] == ["aimlapi", "z.ai"]


def test_operator_can_order_the_chain_by_hand(monkeypatch):
    _cfg(monkeypatch, providers=[
        {"name": "groq", "base_url": "https://api.groq.com/openai/v1", "env": ["GROQ_API_KEY"]},
        {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"]},
    ])
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("Z_AI_API_KEY", "z")
    assert [t["name"] for t in pc.chain()] == ["groq", "z.ai"]


# ── clasificar la avería: agotado ≠ rate-limit pasajero (misma regla que el hermano de workers) ─────────────
def test_a_passing_rate_limit_does_not_burn_a_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    assert pc.classify_failure(BARE_429) == "rate"
    assert pc.note_failure(BARE_429) is None            # se reintenta solo, no se releva
    assert pc.pick()["name"] == "z.ai"


def test_a_task_failure_is_not_a_provider_failure():
    assert pc.classify_failure("no encontré ningún parque acuático abierto hoy") == ""
    assert pc.note_failure("no encontré ningún parque acuático abierto hoy") is None


# ── el relevo ─────────────────────────────────────────────────────────────────────────────────────────────
def test_exhaustion_hands_over_and_respects_the_providers_own_reset_date(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    assert pc.pick()["name"] == "z.ai"

    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic"})
    assert nxt["name"] == "aimlapi"
    assert pc.pick()["name"] == "aimlapi"               # el siguiente turno ya arranca en el relevo (STICKY)
    assert pc._cooldown["z.ai"] == time.mktime(time.strptime("2026-08-04", "%Y-%m-%d"))


def test_without_a_reset_date_it_retries_in_a_while(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure("insufficient credit", {"name": "z.ai", "base_url": "x"})
    assert time.time() < pc._cooldown["z.ai"] <= time.time() + pc._DEFAULT_COOLDOWN_S + 1


def test_no_tier_left_returns_none(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    nxt = pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    assert nxt is None
    assert pc.pick() is None


def test_clear_lets_the_operator_resume_after_topping_up(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    pc.clear("z.ai")
    assert pc.pick()["name"] == "z.ai"


def test_spec_for_carries_model_and_credential(monkeypatch):
    monkeypatch.setenv("Z_AI_API_KEY", "zzz")
    tier = {"name": "z.ai", "base_url": "https://api.z.ai/api/anthropic", "model": "glm-5.2", "env": ["Z_AI_API_KEY"]}
    spec = pc.spec_for(tier)
    assert spec.model == "glm-5.2" and spec.base_url == "https://api.z.ai/api/anthropic" and spec.api_key == "zzz"


# ── y que el PANEL se entere ──────────────────────────────────────────────────────────────────────────────
def test_the_alerts_panel_surfaces_an_exhausted_cluster_provider(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    monkeypatch.setenv("AIMLAPI_KEY", "k2")
    from config import balances
    assert not [a for a in balances.cluster_providers() if a["state"] == "error"]

    pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    rows = balances.cluster_providers()
    bad = [r for r in rows if r["state"] == "error"]
    assert bad and bad[0]["key"] == "cluster:z.ai" and "cuota" in bad[0]["detail"]
    assert [r for r in rows if r["state"] == "ok" and "EN USO" in r["detail"]]


def test_no_tier_left_is_its_own_loud_alert(monkeypatch):
    _cfg(monkeypatch)
    monkeypatch.setenv("Z_AI_API_KEY", "k")
    pc.note_failure(REAL_429_EXHAUSTED, {"name": "z.ai", "base_url": "x"})
    from config import balances
    assert any(r["key"] == "cluster:sin-relevo" for r in balances.cluster_providers())
