"""V2-462 — el juez gasta el PLAN de Z.AI antes que los CRÉDITOS, y los créditos antes que cambiar de modelo.

Norma del operador (2026-08-28): «usar el plan básico y cuando se acaba o se bloquea pasamos a usar los
créditos que tenemos disponibles en ZAI». Medido ese día con el plan agotado y $20 de créditos recién
puestos:

  · el endpoint del plan (Anthropic-compatible) devuelve `1310 Weekly/Monthly Limit Exhausted … reset at
    2026-09-01` y NO cae a créditos solo — el forfait es un muro, no una cuesta;
  · los créditos NO sirven el endpoint del plan: viven en paas/v4, OpenAI-compatible, con la MISMA key;
  · en paas/v4 glm-4.6 RAZONA por defecto: una sonda de 10 tokens volvió con `content: ""` y todo en
    `reasoning_content` — un 200 con forma de respuesta que parsea como nada. `thinking: disabled` es
    parte del contrato de la pata, no una opción.

La pata va ENTRE el plan y DeepSeek y no después, por comparabilidad: es el MISMO modelo con otra cartera,
así que las notas del tablero siguen siendo comparables — que es justo lo que caer a DeepSeek no da.
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


# ── el orden ────────────────────────────────────────────────────────────────────────────────────────────
def test_plan_agotado_los_creditos_juzgan_ANTES_que_deepseek(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(L, "glm_call", lambda *a, **k: order.append("plan") or _plan_bloqueado())
    monkeypatch.setattr(L, "glm_credits_call", lambda *a, **k: order.append("créditos") or '{"ok":true}')
    monkeypatch.setattr(L, "deepseek_direct_call", lambda *a, **k: order.append("deepseek") or "{}")
    txt, model = L.judge_call([{"role": "user", "content": "x"}])
    assert order == ["plan", "créditos"], "los créditos son la continuación del plan, no el último recurso"
    assert txt == '{"ok":true}'


def test_el_modelo_reportado_es_EL_MISMO_porque_solo_cambio_la_cartera(monkeypatch):
    """La razón de que la pata vaya aquí y no detrás de DeepSeek: el tablero compara notas por modelo, y un
    relevo que cambia de cartera sin cambiar de modelo mantiene las rondas comparables."""
    monkeypatch.setattr(L, "glm_call", _plan_bloqueado)
    monkeypatch.setattr(L, "glm_credits_call", lambda *a, **k: '{"ok":true}')
    _, model = L.judge_call([{"role": "user", "content": "x"}])
    assert model == "glm-4.6"


def test_con_el_plan_VIVO_los_creditos_no_se_gastan(monkeypatch):
    """La mitad de sensibilidad, y la que protege los $20: mientras el forfait responda, la cartera de pago
    por uso no se toca."""
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
    """La regla que las otras dos patas ya llevan (2026-08-20/26): un cuerpo vacío se relanza, no se
    devuelve. Sin esto, el 200-con-nada de un razonador pararía la cadena justo en la pata nueva."""
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


# ── el contrato de la petición ──────────────────────────────────────────────────────────────────────────
def test_la_pata_va_a_paas_v4_con_el_razonamiento_APAGADO(monkeypatch):
    """Las dos cosas que se midieron el 2026-08-28 y que, faltando cualquiera, la pata contesta nada:
    la URL (los créditos no viven en el endpoint del plan) y `thinking: disabled` (glm-4.6 razona por
    defecto en paas/v4 y se come el presupuesto entero sin error)."""
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
