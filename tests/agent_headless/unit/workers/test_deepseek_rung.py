"""The DeepSeek relay rung declares a model its gateway actually serves (2026-08-14).

This rung sat in `providers.KNOWN` from 2026-08-13 **written but never exercised**, because it only activates when
`DEEPSEEK_API_KEY` is present and there was no key. The moment the credential landed it went live — and it was
broken:

    model="sonnet" → 400 «The supported API model names are deepseek-v4-pro or deepseek-v4-flash,
                          but you passed sonnet.»

The comment above it asserted that the gateway maps Claude aliases (`claude-sonnet*` → v4-flash). It does not.
Verified against the live endpoint: every Claude alias 400s; `deepseek-v4-flash`/`deepseek-v4-pro` both 200.

**Why this is worth a test of its own.** A relay rung is only ever reached when the primary provider is already
down, so a broken one turns a partial outage into a total one — and it fails with "the worker died instantly",
which points nowhere near the model name. The class of bug is "configuration that has never executed", and the
cheap guard is a static one: check the declared name is a name the provider admits, without needing the network.
"""
from __future__ import annotations

from nucleo.workers import providers

# The only two names `api.deepseek.com` admits, on both its OpenAI-compatible and its Anthropic-compatible
# surfaces. Probed directly (GET /models and a real POST): there is no alias family.
DEEPSEEK_MODELS = {"deepseek-v4-flash", "deepseek-v4-pro"}

# Aliases that LOOK plausible and are rejected. Kept explicit so nobody "restores" one of them from the old comment.
REJECTED = {"sonnet", "opus", "claude-sonnet-4", "claude-sonnet-4.5"}


def _rung(name: str) -> dict:
    for t in providers.KNOWN:
        if t.get("name") == name:
            return t
    raise AssertionError(f"rung {name!r} disappeared from providers.KNOWN")


def test_el_escalon_deepseek_declara_un_modelo_que_su_gateway_SIRVE():
    m = (_rung("deepseek").get("model") or "").strip()
    assert m in DEEPSEEK_MODELS, (
        f"el escalón DeepSeek declara model={m!r}, que su gateway rechaza con 400. Admite solo {DEEPSEEK_MODELS}. "
        f"Este escalón solo se usa cuando el titular YA cayó, así que un nombre inválido aquí convierte una caída "
        f"parcial en total.")
    assert m not in REJECTED


def test_no_se_cuela_un_alias_de_claude_en_el_escalon_deepseek():
    """The specific error that occurred: the Claude alias seems reasonable because the endpoint IS Anthropic-compatible.
    Compatible in the PROTOCOL does not mean compatible in the CATALOG."""
    m = (_rung("deepseek").get("model") or "").lower()
    assert "sonnet" not in m and "opus" not in m and "claude" not in m, (
        f"model={m!r}: el gateway de DeepSeek habla el protocolo de Anthropic pero NO sirve sus modelos")


def test_deepseek_va_DESPUES_de_los_planes_de_suscripcion():
    """Operator rule: “SUBSCRIPTION plans (forfait), never pay-per-token.” DeepSeek is pay-per-token, so it is
    an inexpensive safety net and cannot move ahead of a forfait that has already been paid for."""
    names = [t.get("name") for t in providers.KNOWN]
    assert "deepseek" in names
    for plan in ("z.ai", "moonshot"):
        if plan in names:
            assert names.index(plan) < names.index("deepseek"), (
                f"{plan} (suscripción) tiene que ir antes que deepseek (pago por token)")


def test_todo_escalon_declara_credencial_y_endpoint():
    """Guarda general del catálogo: un escalón sin `env` se consideraría siempre disponible y se elegiría aunque no
    haya credencial; uno sin `base_url` caería a la licencia local, que en la nube no existe."""
    for t in providers.KNOWN:
        assert t.get("base_url"), f"{t.get('name')}: sin base_url"
        assert t.get("env"), f"{t.get('name')}: sin variables de credencial declaradas"
