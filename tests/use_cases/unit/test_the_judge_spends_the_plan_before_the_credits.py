"""V2-462 — the judge spends the Z.AI PLAN before the CREDITS, and the credits before switching models.

Operator rule (2026-08-28): “use the basic plan and when it runs out or is blocked, switch to using the
credits available in ZAI”. Measured that day with the plan exhausted and $20 in newly added credits:

  · the plan endpoint (Anthropic-compatible) returns `1310 Weekly/Monthly Limit Exhausted … reset at
    2026-09-01` and does NOT fall back to credits alone — the forfait is a wall, not a slope;
  · credits do NOT serve the plan endpoint: they live at paas/v4, OpenAI-compatible, with the SAME key;
  · at paas/v4 glm-4.6 REASONS by default: a 10-token probe returned `content: ""` and everything in
    `reasoning_content` — a 200 with the shape of a response that parses as nothing. `thinking: disabled` is
    part of the leg’s contract, not an option.

The leg goes BETWEEN the plan and DeepSeek, not after it, for comparability: it is the SAME model with a
different wallet, so the board’s scores remain comparable — exactly what falling back to DeepSeek does not provide.
"""
from __future__ import annotations

import io
import json
import urllib.request

import pytest

from tests.voice.e2e.agent import llm as L


@pytest.fixture(autouse=True)
def _zai_configured(monkeypatch):
    monkeypatch.setattr(L.config, "JUDGE_PROVIDER", "zai", raising=False)
    monkeypatch.setattr(L.config, "ZAI_KEY", "k-zai", raising=False)
    monkeypatch.setattr(L.config, "ZAI_JUDGE_MODEL", "glm-4.6", raising=False)
    monkeypatch.setattr(L.config, "ZAI_PAAS_BASE", "https://api.z.ai/api/paas/v4", raising=False)
    monkeypatch.setattr(L.config, "DEEPSEEK_KEY", "k-ds", raising=False)
    import time
    monkeypatch.setattr(time, "sleep", lambda s: None)


def _plan_bloqueado(*a, **k):
    raise RuntimeError("HTTP Error 429: [1310][Weekly/Monthly Limit Exhausted. reset at 2026-09-01]")


# ── the order ────────────────────────────────────────────────────────────────────────────────────────────
def test_plan_agotado_los_creditos_juzgan_ANTES_que_deepseek(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(L, "glm_call", lambda *a, **k: order.append("plan") or _plan_bloqueado())
    monkeypatch.setattr(L, "glm_credits_call", lambda *a, **k: order.append("créditos") or '{"ok":true}')
    monkeypatch.setattr(L, "deepseek_direct_call", lambda *a, **k: order.append("deepseek") or "{}")
    txt, model = L.judge_call([{"role": "user", "content": "x"}])
    assert order == ["plan", "créditos"], "los créditos son la continuación del plan, no el último recurso"
    assert txt == '{"ok":true}'


def test_el_modelo_reportado_es_EL_MISMO_porque_solo_cambio_la_cartera(monkeypatch):
    """Why the leg goes here and not behind DeepSeek: the board compares scores by model, and a
    handoff that changes wallets without changing models keeps the rounds comparable."""
    monkeypatch.setattr(L, "glm_call", _plan_bloqueado)
    monkeypatch.setattr(L, "glm_credits_call", lambda *a, **k: '{"ok":true}')
    _, model = L.judge_call([{"role": "user", "content": "x"}])
    assert model == "glm-4.6"


def test_con_el_plan_VIVO_los_creditos_no_se_gastan(monkeypatch):
    """The more sensitive half, and the one that protects the $20: while the forfait responds, the
    pay-as-you-go wallet is not touched."""
    called: list[str] = []
    monkeypatch.setattr(L, "glm_call", lambda *a, **k: called.append("plan") or '{"ok":true}')
    monkeypatch.setattr(L, "glm_credits_call", lambda *a, **k: called.append("créditos") or "{}")
    L.judge_call([{"role": "user", "content": "x"}])
    assert called == ["plan"]


def test_creditos_agotados_se_cae_a_deepseek_sin_perder_la_ronda(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(L, "glm_call", _plan_bloqueado)

    def _sin_saldo(*a, **k):
        order.append("créditos")
        raise RuntimeError("HTTP Error 429: 1113 Insufficient balance or no resource package")

    monkeypatch.setattr(L, "glm_credits_call", _sin_saldo)
    monkeypatch.setattr(L, "deepseek_direct_call", lambda *a, **k: order.append("deepseek") or '{"ok":true}')
    txt, model = L.judge_call([{"role": "user", "content": "x"}])
    assert order == ["créditos", "deepseek"]
    assert model == L.config.DEEPSEEK_JUDGE_MODEL


def test_un_200_vacio_de_los_creditos_NO_es_un_veredicto(monkeypatch):
    """The rule already implemented by the other two legs (2026-08-20/26): an empty body is retried, not
    returned. Without this, the reasoner’s 200-with-nothing would stop the chain at the new leg."""
    order: list[str] = []
    monkeypatch.setattr(L, "glm_call", _plan_bloqueado)
    monkeypatch.setattr(L, "glm_credits_call", lambda *a, **k: order.append("créditos") or "   ")
    monkeypatch.setattr(L, "deepseek_direct_call", lambda *a, **k: order.append("deepseek") or '{"ok":true}')
    L.judge_call([{"role": "user", "content": "x"}])
    assert order == ["créditos", "deepseek"]


def test_sin_key_de_zai_no_hay_pata_de_creditos():
    with pytest.raises(RuntimeError):
        import tests.voice.e2e.agent.llm as LL
        _saved = LL.config.ZAI_KEY
        try:
            LL.config.ZAI_KEY = ""
            LL.glm_credits_call([{"role": "user", "content": "x"}])
        finally:
            LL.config.ZAI_KEY = _saved


# ── the request contract ──────────────────────────────────────────────────────────────────────────
def test_la_pata_va_a_paas_v4_con_el_razonamiento_APAGADO(monkeypatch):
    """The two things measured on 2026-08-28 that, if either is missing, cause the leg to answer nothing:
    the URL (credits do not live at the plan endpoint) and `thinking: disabled` (glm-4.6 reasons by
    default at paas/v4 and consumes the entire budget without an error)."""
    seen: dict = {}

    def _urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["payload"] = json.loads(req.data)
        seen["auth"] = req.get_header("Authorization")
        body = json.dumps({"choices": [{"message": {"content": '{"ok":true}'},
                                        "finish_reason": "stop"}]}).encode()
        class _R(io.BytesIO):
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        return _R(body)

    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    out: dict = {}
    txt = L.glm_credits_call([{"role": "user", "content": "x"}], out=out)
    assert txt == '{"ok":true}'
    assert seen["url"] == "https://api.z.ai/api/paas/v4/chat/completions"
    assert seen["payload"]["thinking"] == {"type": "disabled"}
    assert seen["payload"]["model"] == "glm-4.6"
    assert seen["auth"] == "Bearer k-zai"
    assert out.get("finish_reason") == "stop", "la palabra del proveedor sobre el corte tiene que viajar"
