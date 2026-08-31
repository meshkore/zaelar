"""V2-458 — two tiers sharing an account are not two tiers.

Measured with the live engine on 2026-08-28: the operator's voice chain contains `deepseek-v4-flash` and
`deepseek-v4-pro`, both using `DEEPSEEK_API_KEY`. With the account at zero, the primary returned 402, the relay
went to the sibling, the sibling returned 402 — and that exhausted the single retry granted by V2-252, so the turn
came out silent **with AIMLAPI returning 200 one row below**.
"""
from __future__ import annotations

import time

import pytest

from nucleo.flash import provider_chain as pc

_402 = ("Error code: 402 - {'error': {'message': 'Insufficient Balance', 'type': 'unknown_error'}}")
_429 = "429 — [1310][Weekly Limit Exhausted. Your limit will reset at 2027-01-01 01:39:02]"


@pytest.fixture()
def cadena(monkeypatch):
    """The operator's REAL chain, in miniature: two tiers from one account and one from another."""
    tiers = [
        {"name": "deepseek-directo", "base_url": "https://api.deepseek.com",
         "model": "deepseek-v4-flash", "api_key": "SECRETO-DEEPSEEK", "plan": "titular"},
        {"name": "deepseek-directo-pro", "base_url": "https://api.deepseek.com",
         "model": "deepseek-v4-pro", "api_key": "SECRETO-DEEPSEEK", "plan": "relevo hermano"},
        {"name": "aimlapi-failover", "base_url": "https://api.aimlapi.com/v1",
         "model": "deepseek/deepseek-v4-flash", "api_key": "SECRETO-AIMLAPI", "plan": "otro proveedor"},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    pc._store.clear() if hasattr(pc._store, "clear") else None
    for t in tiers:
        pc._store.set(t["name"], 0, pc._health.REASON_HEALTH)
    return tiers


def test_un_saldo_agotado_apaga_a_los_hermanos_de_la_MISMA_cuenta(cadena, monkeypatch):
    nxt = pc.note_failure(_402, cadena[0], role=pc.ROLE_VOICE)
    assert nxt is not None, "tiene que haber relevo: AIMLAPI es otra cuenta y está sana"
    assert nxt["name"] == "aimlapi-failover", (
        "el relevo se saltó al hermano de la misma cuenta, que es lo que costaba el turno")
    assert not pc._store.available("deepseek-directo-pro"), "el hermano gasta del mismo saldo: cae con él"
    assert pc._store.available("aimlapi-failover"), "otra cuenta no tiene por qué caer"


def test_una_CUOTA_agotada_NO_arrastra_a_nadie(cadena):
    """The distinction from V2-243, which this change must not erase: a quota belongs to the MODEL and replenishes itself.

    Without this half, “shut down those sharing an account” would shut down half the chain every time a specific model
    reaches its weekly limit — and that limit says nothing about the model next to it.
    """
    pc.note_failure(_429, cadena[0], role=pc.ROLE_VOICE)
    assert not pc._store.available("deepseek-directo")
    assert pc._store.available("deepseek-directo-pro"), "una cuota del flash no agota la del pro"


def test_sin_credencial_resoluble_no_se_apaga_a_nadie(cadena, monkeypatch):
    """“I don't know” can never shut down a healthy tier: without a credential to compare, it is not paired."""
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [
        {**cadena[0], "api_key": ""}, dict(cadena[1]), dict(cadena[2])])
    monkeypatch.setattr(pc, "_token_for", lambda t: "")
    pc.note_failure(_402, {**cadena[0], "api_key": ""}, role=pc.ROLE_VOICE)
    assert pc._store.available("deepseek-directo-pro")


def _aviso(cadena) -> str:
    """What is REPORTED, captured from the real emitter.

    It is collected through `emit`, not `caplog`: this repo logs with loguru, which does not go through the stdlib's
    logging — so a `caplog` here returns an EMPTY string and anything asserted about it passes without checking
    anything. The first version of the two cases below did exactly that, and the secret case is the painful one:
    it would have certified that a credential was not leaked without reading a single character.
    """
    visto = []
    import voice.observer as obs
    orig = obs.emit
    obs.emit = lambda *a, **k: visto.append(" ".join(str(x) for x in a) + " " + str(k))
    try:
        pc.note_failure(_402, cadena[0], role=pc.ROLE_VOICE)
    finally:
        obs.emit = orig
    return " ".join(visto)


def test_el_aviso_NOMBRA_a_los_que_se_lleva_por_delante(cadena):
    """Two tiers shut down and one named leaves the operator looking for why the other one does not respond either."""
    texto = _aviso(cadena)
    assert texto, "el aviso tiene que existir, o los dos casos de abajo no miden nada"
    assert "deepseek-directo-pro" in texto and "misma cuenta" in texto


def test_el_secreto_no_sale_en_el_aviso(cadena):
    texto = _aviso(cadena)
    assert texto
    assert "SECRETO-DEEPSEEK" not in texto


def test_dos_escalones_que_nombran_la_clave_distinto_pero_resuelven_igual_son_la_misma_cuenta(monkeypatch):
    """The RESOLVED credentials are compared, not the names of the environment variables."""
    tiers = [
        {"name": "a", "base_url": "https://api.mismo.com/v1", "env": ["CLAVE_UNO"], "plan": ""},
        {"name": "b", "base_url": "https://api.mismo.com/v2", "env": ["CLAVE_DOS"], "plan": ""},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    monkeypatch.setattr(pc, "_token_for", lambda t: "el-mismo-valor")
    assert pc._same_account_as(tiers[0], pc.ROLE_VOICE) == ["b"]


def test_la_misma_clave_en_PROVEEDORES_distintos_no_los_hace_la_misma_cuenta(monkeypatch):
    """The part that makes the rule safe, and is not hypothetical: an existing test exposed it.

    `test_the_text_channel_relays_too` seeds `Z_AI_API_KEY` and `AIMLAPI_KEY` with the SAME literal, so a rule
    that looked only at the credential would have shut down Z.AI when AIMLAPI failed — a healthy provider removed from
    the game because of a coincidence of values. That is why the host is also necessary.
    """
    tiers = [
        {"name": "zai", "base_url": "https://api.z.ai/api/anthropic", "env": ["Z_AI_API_KEY"], "plan": ""},
        {"name": "aimlapi", "base_url": "https://api.aimlapi.com/v1", "env": ["AIMLAPI_KEY"], "plan": ""},
    ]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    monkeypatch.setattr(pc, "_token_for", lambda t: "la-misma-k")
    assert pc._same_account_as(tiers[0], pc.ROLE_VOICE) == []


def test_sin_host_no_se_empareja_con_nadie(monkeypatch):
    tiers = [{"name": "a", "base_url": "", "api_key": "k", "plan": ""},
             {"name": "b", "base_url": "", "api_key": "k", "plan": ""}]
    monkeypatch.setattr(pc, "chain", lambda role=pc.ROLE_CLUSTER: [dict(t) for t in tiers])
    assert pc._same_account_as(tiers[0], pc.ROLE_VOICE) == []
