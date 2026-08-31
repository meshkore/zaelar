"""Tests for config/balances.py (V2-043) — structure, fail-open behavior, and reactive classification. No real network.

Canonical location: tests/infrastructure/unit/config/.
"""
from config import balances


def test_summary_shape_and_failopen(monkeypatch):
    # doctor.credentials fails → summary does NOT raise; it returns an empty list.
    monkeypatch.setattr("config.doctor.credentials", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    out = balances.summary()
    assert out == []


def test_summary_marks_off_without_key(monkeypatch):
    monkeypatch.setattr("config.doctor.credentials",
                        lambda: [{"key": "elevenlabs", "enables": "TTS", "profiles": [], "env": ["ELEVENLABS_API_KEY"], "set": False}])
    out = balances.summary()
    assert len(out) == 1 and out[0]["state"] == "off" and out[0]["set"] is False


def test_reactive_credit_overrides_ok(monkeypatch):
    # key present + a recent 'credit' error in health_state → error state «SIN SALDO», not ok.
    monkeypatch.setattr("config.doctor.credentials",
                        lambda: [{"key": "aimlapi", "enables": "LLM", "profiles": [], "env": ["AIMLAPI_KEY"], "set": True}])

    class _HS:
        @staticmethod
        def get(k):
            return {"kind": "credit", "text": "429 too many requests"} if k == "llm" else None
    import sys

    import voice
    # BOTH must be replaced: `balances` does `from voice import health_state`, which reads the package ATTRIBUTE,
    # not `sys.modules` — patching only sys.modules had no effect once another test had imported the module
    # earlier (since 2026-08-02 the worker's provider handoff imports it), and the test passed/failed depending on
    # collection order.
    monkeypatch.setitem(sys.modules, "voice.health_state", _HS)
    monkeypatch.setattr(voice, "health_state", _HS, raising=False)
    out = {s["key"]: s for s in balances.summary()}
    assert out["aimlapi"]["state"] == "error"
    assert "SIN SALDO" in out["aimlapi"]["detail"]


def test_balance_unknown_for_unprobed_provider():
    # a service without a declared probe → unknown; never raises.
    assert balances.balance("aimlapi")["state"] == "unknown"


def test_alerts_is_subset_of_summary(monkeypatch):
    monkeypatch.setattr("config.doctor.credentials",
                        lambda: [{"key": "brave", "enables": "search", "profiles": [], "env": ["BRAVE_SEARCH_KEY"], "set": False}])
    assert all(a["state"] in ("warn", "error") for a in balances.alerts())
