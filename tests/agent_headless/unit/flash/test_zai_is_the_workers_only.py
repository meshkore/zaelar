"""V2-496 — Z.AI es del BRAIN WORKER y de nadie más.

Norma del operador, 2026-08-30, literal:

    «el proveedor de Z.AI solo sirve para el Brain Worker, para utilizarse dentro de Claude Code; no sirve
     como failover de nada más y no se debe utilizar en ningún otro apartado del agente.»

Deroga a V2-462, que había puesto las DOS carteras de Z.AI en la cadena de VOZ (plan por `api/anthropic`,
créditos por `paas/v4`). Aquello funcionaba —demasiado bien—: la voz relevaba sola a los créditos, y así fue
como bajó el saldo de una cartera que no estaba autorizada para eso. El operador lo vio en el panel de Z.AI
antes que nosotros en el código.

Lo MEDIDO que hay que tener delante antes de tocar esto (2026-08-29/30, en vivo):

  · plan agotado → `429 · 1310 Weekly/Monthly Limit Exhausted, reset 2026-09-01 01:39`, y **no cae a
    créditos solo**: son dos carteras y dos endpoints;
  · créditos con saldo → `200` por `paas/v4`, que es **OpenAI-compatible**;
  · el worker lo conduce el CLI de Claude Code, que habla **protocolo Anthropic**. Por eso el escalón de
    créditos NO se puede mudar al worker de un renglón: acabaría en `/v1/messages` de un endpoint que no lo
    sirve, o sea un 404 con pinta de caída, justo en el escalón de socorro. Queda declarado y sin construir.

Este fichero fija la propiedad NEGATIVA —dónde Z.AI no puede aparecer—, que es la que se rompe sola: un
escalón se añade «porque hay credencial» y nadie se entera hasta que baja el saldo.
"""
from __future__ import annotations

from nucleo.flash import provider_chain as PC
from nucleo.workers import providers as WP


def _zai(t: dict) -> bool:
    return "api.z.ai" in (t.get("base_url") or "")


# ── donde NO puede estar ────────────────────────────────────────────────────────────────────────────────

def test_la_cadena_de_voz_no_lleva_ZAI():
    """`_known_chain()` sirve al cerebro de voz, al compositor del brief y al cerebro de cluster."""
    assert not [t for t in PC._known_chain() if _zai(t)], (
        "Z.AI ha vuelto a la cadena que NO es la del worker; ahí gasta saldo sin autorización")


def test_ningun_relevo_de_voz_lleva_ZAI():
    """Los escalones de relevo por latencia son otra lista, y por eso hay que mirarla aparte: la norma se
    rompería igual de bien colándolo por ahí."""
    assert not [t for t in PC._VOICE_RELAYS() if _zai(t)]


def test_el_motor_de_voz_no_ofrece_un_proveedor_ZAI():
    """Había un proveedor `glm` registrado (Z.AI, OpenAI-compatible) seleccionable como cerebro de voz. Se
    retiró: además de esta norma, era un RAZONADOR ofrecido para la voz, que ya violaba la regla dura."""
    from voice.engine.llm import providers as _p  # noqa: F401 — el import registra los proveedores
    from voice.engine.llm import registry
    assert "glm" not in set(registry.names())


def test_los_ajustes_de_ZAI_no_viven_en_la_config_de_voz():
    """Un ajuste sin proveedor que lo lea es una invitación a volver a enchufarlo."""
    from voice.engine.core.config import SETTINGS
    for campo in ("zai_api_key", "zai_base_url", "glm_model"):
        assert not hasattr(SETTINGS, campo), f"«{campo}» sigue en la config de voz"


# ── donde SÍ tiene que estar ────────────────────────────────────────────────────────────────────────────

def test_el_worker_SIGUE_teniendo_su_escalon_de_ZAI():
    """La otra mitad, y no es simetría: quitarlo de todas partes dejaría al Brain Worker sin su titular."""
    zai = [t for t in WP.KNOWN if _zai(t)]
    assert zai, "el worker se ha quedado sin Z.AI: eso no es la norma, es lo contrario"
    assert all("anthropic" in t["base_url"] for t in zai), (
        "el worker habla protocolo Anthropic; un endpoint OpenAI aquí es un 404 con pinta de caída")
    assert all(t.get("vision") is False for t in zai), (
        "el rasgo medido de GLM —confabula sobre imágenes que no ve— no puede perderse al reordenar")


# ── el agujero que dejó al quitarlo ──────────────────────────────────────────────────────────────────────

def test_el_catalogo_por_defecto_encabeza_con_DEEPSEEK_DIRECTO(monkeypatch):
    """Quitar Z.AI dejó de cabeza al broker AIMLAPI — y esa misma noche AIMLAPI estaba caído (curl a pelo:
    45 s y HTTP 000) mientras `api.deepseek.com` contestaba en 0,68 s. El turno se quedaba en
    `APITimeoutError` con el titular bueno a un renglón.

    La causa no fue quitar Z.AI: fue que este catálogo llevaba tiempo **desalineado con el reparto canónico**
    —«FlashBrain: DeepSeek directo → v4-pro → AIMLAPI failover»— y Z.AI le tapaba el hueco. Un fallo así solo
    se ve el día que se mueve la pieza de encima."""
    for var in ("MESHKORE_MISSION_MODEL", "ASSISTANT_LLM_MODEL", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    names = [t["name"] for t in PC._known_chain()]
    assert names[0] == "deepseek-directo", f"el titular de voz no encabeza el catálogo: {names}"
    assert names == ["deepseek-directo", "aimlapi-failover"], (
        f"la cadena de voz tiene que ser titular + UN failover, y es {names} — norma del operador 2026-08-30")
