"""V2-496 — Z.AI belongs to the BRAIN WORKER and nobody else.

Operator's rule, 2026-08-30, verbatim:

    «the Z.AI provider is only for the Brain Worker, to be used within Claude Code; it is not a failover
     for anything else and must not be used in any other part of the agent.»

It supersedes V2-462, which had put BOTH Z.AI accounts in the VOICE chain (plan via `api/anthropic`,
credits via `paas/v4`). That worked —too well—: voice switched over to credits on its own, and that is how
the balance of an account not authorized for that purpose was reduced. The operator saw it in the Z.AI
dashboard before we saw it in the code.

The MEASURED facts to keep in view before touching this (2026-08-29/30, live):

  · plan exhausted → `429 · 1310 Weekly/Monthly Limit Exhausted, reset 2026-09-01 01:39`, and **it does not
    fall back to credits alone**: these are two accounts and two endpoints;
  · credits with balance → `200` via `paas/v4`, which is **OpenAI-compatible**;
  · the worker is driven by the Claude Code CLI, which speaks **the Anthropic protocol**. Therefore the
    credits step cannot be moved to the worker as a one-line change: it would end up at `/v1/messages` on an
    endpoint that does not serve it, meaning a 404 that looks like an outage, precisely at the rescue step.
    It is declared but not built.

This file establishes the NEGATIVE property —where Z.AI must not appear—which is the one that breaks on its
own: a step gets added «because there is a credential» and nobody notices until the balance drops.
"""
from __future__ import annotations

from nucleo.flash import provider_chain as PC
from nucleo.workers import providers as WP


def _zai(t: dict) -> bool:
    return "api.z.ai" in (t.get("base_url") or "")


# ── where it must NOT be ─────────────────────────────────────────────────────────────────────────────────

def test_la_cadena_de_voz_no_lleva_ZAI():
    """`_known_chain()` serves the voice brain, the brief composer, and the cluster brain."""
    assert not [t for t in PC._known_chain() if _zai(t)], (
        "Z.AI ha vuelto a la cadena que NO es la del worker; ahí gasta saldo sin autorización")


def test_ningun_relevo_de_voz_lleva_ZAI():
    """The latency-based relay steps are a separate list, so it must be checked separately: the rule would
    be just as easily broken by slipping it in there."""
    assert not [t for t in PC._VOICE_RELAYS() if _zai(t)]


def test_el_motor_de_voz_no_ofrece_un_proveedor_ZAI():
    """A `glm` provider (Z.AI, OpenAI-compatible) was registered and selectable as the voice brain. It was
    removed: in addition to violating this rule, it was a REASONER offered for voice, which already violated
    the hard rule."""
    from voice.engine.llm import providers as _p  # noqa: F401 — the import registers the providers
    from voice.engine.llm import registry
    assert "glm" not in set(registry.names())


def test_los_ajustes_de_ZAI_no_viven_en_la_config_de_voz():
    """A setting with no provider to read it is an invitation to plug it back in."""
    from voice.engine.core.config import SETTINGS
    for campo in ("zai_api_key", "zai_base_url", "glm_model"):
        assert not hasattr(SETTINGS, campo), f"«{campo}» sigue en la config de voz"


# ── where it MUST be ─────────────────────────────────────────────────────────────────────────────────────

def test_el_worker_SIGUE_teniendo_su_escalon_de_ZAI():
    """The other half, and this is not symmetry: removing it everywhere would leave the Brain Worker without
    its primary provider."""
    zai = [t for t in WP.KNOWN if _zai(t)]
    assert zai, "el worker se ha quedado sin Z.AI: eso no es la norma, es lo contrario"
    assert all("anthropic" in t["base_url"] for t in zai), (
        "el worker habla protocolo Anthropic; un endpoint OpenAI aquí es un 404 con pinta de caída")
    assert all(t.get("vision") is False for t in zai), (
        "el rasgo medido de GLM —confabula sobre imágenes que no ve— no puede perderse al reordenar")


# ── the gap left by removing it ──────────────────────────────────────────────────────────────────────────

def test_el_catalogo_por_defecto_encabeza_con_DEEPSEEK_DIRECTO(monkeypatch):
    """Removing Z.AI put the AIMLAPI broker at the top — and that same night AIMLAPI was down (a raw curl:
    45 s and HTTP 000) while `api.deepseek.com` responded in 0.68 s. The turn stalled on
    `APITimeoutError` with the good primary provider one line below.

    The cause was not removing Z.AI: this catalog had long been **misaligned with the canonical allocation**
    —«FlashBrain: direct DeepSeek → v4-pro → AIMLAPI failover»— and Z.AI had been masking the gap. A failure
    like this is only visible on the day the piece on top is moved."""
    for var in ("MESHKORE_MISSION_MODEL", "ASSISTANT_LLM_MODEL", "LLM_MODEL", "LLM_API_KEY", "LLM_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    names = [t["name"] for t in PC._known_chain()]
    assert names[0] == "deepseek-directo", f"el titular de voz no encabeza el catálogo: {names}"
    assert names == ["deepseek-directo", "aimlapi-failover"], (
        f"la cadena de voz tiene que ser titular + UN failover, y es {names} — norma del operador 2026-08-30")
