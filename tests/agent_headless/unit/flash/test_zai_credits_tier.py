"""V2-462 — el escalón de CRÉDITOS de Z.AI: mismo modelo, otra cartera, otro protocolo.

Norma del operador (2026-08-28): plan primero, créditos al agotarse. Lo medido que hace falta tener delante
para tocar esto:

  · el plan (endpoint Anthropic) agotado devuelve `1310 … reset at 2026-09-01` y NO cae a créditos solo;
  · los créditos viven en `paas/v4` (OpenAI-compatible) con la MISMA `Z_AI_API_KEY` — misma cuenta, dos
    carteras y dos protocolos en el mismo host.

Ese último punto cruza con DOS mecanismos que ya existían y que, sin cuidado, matarían el escalón:

  · `model_spec._is_zai()` casaba por HOST y habría mandado paas/v4 a `/v1/messages` → un 404 con pinta de
    caída, justo en el escalón de socorro;
  · V2-458 apaga a los hermanos de la misma cuenta cuando uno se queda SIN SALDO — y plan y créditos SON la
    misma cuenta. Lo que lo salva es que `is_depleted` exige que el proveedor no anuncie su vuelta: el 1310
    anuncia el reset, así que agota el escalón del plan sin arrastrar al de créditos.
"""
from __future__ import annotations

from nucleo.flash import provider_chain as PC
from nucleo.flash.fast_client import ModelSpec
from nucleo.workers.providers import is_depleted


# ── la cadena ───────────────────────────────────────────────────────────────────────────────────────────
def test_los_creditos_van_DETRAS_del_plan_y_DELANTE_de_cambiar_de_proveedor():
    names = [t["name"] for t in PC._known_chain()]
    i_plan, i_cred = names.index("z.ai"), names.index("z.ai-créditos")
    assert i_plan < i_cred, "el forfait se gasta antes que la cartera de pago por uso"
    assert i_cred < names.index("aimlapi"), "los créditos son la continuación del plan, no el último recurso"


def test_mismo_modelo_misma_key_distinta_cartera():
    """Un relevo que cambia de modelo cambia de CONDUCTA; este solo cambia de cartera. Y la key compartida
    no es un descuido: es la misma cuenta de Z.AI con dos formas de pago."""
    chain = {t["name"]: t for t in PC._known_chain()}
    plan, cred = chain["z.ai"], chain["z.ai-créditos"]
    assert plan["model"] == cred["model"]
    assert plan["env"] == cred["env"] == ["Z_AI_API_KEY"]
    assert "paas/v4" in cred["base_url"] and "anthropic" in plan["base_url"]


# ── el protocolo ────────────────────────────────────────────────────────────────────────────────────────
def test_el_plan_habla_anthropic_y_los_creditos_NO():
    """La trampa que habría matado el escalón sin ruido: `_is_zai()` casaba por host, y por host los dos son
    api.z.ai — paas/v4 habría acabado en `/v1/messages`, que no existe ahí, con un 404 con pinta de caída en
    el único momento en que el escalón se usa (el plan ya agotado)."""
    plan = ModelSpec(model="glm-5.3", base_url="https://api.z.ai/api/anthropic", api_key="k", provider="zai")
    cred = ModelSpec(model="glm-5.3", base_url="https://api.z.ai/api/paas/v4", api_key="k", provider="aimlapi")
    assert plan._is_zai() is True
    assert cred._is_zai() is False, "paas/v4 es OpenAI-compatible: va por el camino genérico, no por /v1/messages"


# ── el cruce con V2-458 ─────────────────────────────────────────────────────────────────────────────────
def test_el_plan_agotado_NO_arrastra_a_los_creditos():
    """Plan y créditos comparten host y credencial — el emparejamiento de V2-458 los ve como una cuenta. Si
    el 1310 contara como SALDO, agotar el plan apagaría el escalón que existe exactamente para ese momento.
    Lo que lo impide es el predicado de `is_depleted`: un agotamiento CON fecha de vuelta es cuota, no saldo."""
    m1310 = "[1310][Weekly/Monthly Limit Exhausted. Your limit will reset at 2026-09-01 01:39:02]"
    assert is_depleted(m1310) is False
    # …y la condición de arrastre de V2-458 solo se evalúa cuando is_depleted es True (`note_failure`):
    # con False, `hermanos` queda vacío por construcción. Se fija la puerta, no la implementación.


def test_los_creditos_sin_saldo_SI_son_saldo():
    """La otra dirección, para que la puerta discrimine de verdad: el 1113 de paas/v4 no anuncia vuelta —
    eso sí es quedarse sin saldo, y ahí V2-458 hace bien en enfriar la cuenta (el plan ya estaba agotado en
    cualquier escenario en que los créditos lleguen a hablar)."""
    assert is_depleted("1113 Insufficient balance or no resource package") is True
