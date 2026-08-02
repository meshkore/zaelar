"""Tests de config/balances.py (V2-043) — estructura, fail-open y clasificación reactiva. Sin red real.

Ubicación canónica: tests/infrastructure/unit/config/.
"""
from config import balances


def test_summary_shape_and_failopen(monkeypatch):
    # doctor.credentials falla → summary NO lanza, devuelve lista vacía.
    monkeypatch.setattr("config.doctor.credentials", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    out = balances.summary()
    assert out == []


def test_summary_marks_off_without_key(monkeypatch):
    monkeypatch.setattr("config.doctor.credentials",
                        lambda: [{"key": "elevenlabs", "enables": "TTS", "profiles": [], "env": ["ELEVENLABS_API_KEY"], "set": False}])
    out = balances.summary()
    assert len(out) == 1 and out[0]["state"] == "off" and out[0]["set"] is False


def test_reactive_credit_overrides_ok(monkeypatch):
    # key presente + un error reciente 'credit' en health_state → estado error «SIN SALDO», no ok.
    monkeypatch.setattr("config.doctor.credentials",
                        lambda: [{"key": "aimlapi", "enables": "LLM", "profiles": [], "env": ["AIMLAPI_KEY"], "set": True}])

    class _HS:
        @staticmethod
        def get(k):
            return {"kind": "credit", "text": "429 too many requests"} if k == "llm" else None
    import sys

    import voice
    # Hay que sustituir AMBOS: `balances` hace `from voice import health_state`, que lee el ATRIBUTO del paquete,
    # no `sys.modules` — parchear solo sys.modules no tenía efecto en cuanto otro test hubiera importado el módulo
    # antes (desde 2026-08-02 lo importa el relevo de proveedores del worker), y el test pasaba/fallaba según el
    # orden de colección.
    monkeypatch.setitem(sys.modules, "voice.health_state", _HS)
    monkeypatch.setattr(voice, "health_state", _HS, raising=False)
    out = {s["key"]: s for s in balances.summary()}
    assert out["aimlapi"]["state"] == "error"
    assert "SIN SALDO" in out["aimlapi"]["detail"]


def test_balance_unknown_for_unprobed_provider():
    # un servicio sin sonda declarada → unknown, nunca lanza.
    assert balances.balance("aimlapi")["state"] == "unknown"


def test_alerts_is_subset_of_summary(monkeypatch):
    monkeypatch.setattr("config.doctor.credentials",
                        lambda: [{"key": "brave", "enables": "search", "profiles": [], "env": ["BRAVE_SEARCH_KEY"], "set": False}])
    assert all(a["state"] in ("warn", "error") for a in balances.alerts())
