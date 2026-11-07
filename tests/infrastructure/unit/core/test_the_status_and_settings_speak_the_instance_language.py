"""The ◉ Status panel and the ⚙ settings speak the INSTANCE language, never a fixed Castilian (2026-10-21).

Every row label and detail of `/api/status`, the API balance lines, the voice knobs, the provider catalog's prose
and the benchmark cards used to be literals written in the server — Spanish for most of them, developer English for
the catalog — so an English instance read «Memoria · CORAZÓN» and a Spanish one read the catalog in English. They
now come from the `ui` pack (active language → English → the literal), which is what lets a THIRD language work:
whatever the onboarding has not generated yet falls back to English, not to Castilian.

Each test sets the language twice: a code with no bundle at all («zz», standing for any generated language that is
not there yet) must read English, and «es» must read exactly the Spanish the panel always showed.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

import pytest

from i18n import runtime as _rt

ENGINE = Path(__file__).resolve().parents[4]
SOURCES = ("server/voice_status.py", "config/balances.py", "config/settings.py")


@pytest.fixture
def lang(monkeypatch):
    real = _rt._store.read
    monkeypatch.setattr(_rt._store, "read", lambda code: {} if code == "zz" else real(code))

    def set_(code: str) -> None:
        monkeypatch.setenv("ZAELAR_LANGUAGE", code)
        _rt.invalidate()

    yield set_
    _rt.invalidate()


def _status_rows() -> dict:
    from server.voice_api import status
    body = json.loads(asyncio.run(status()).body)
    return {it["key"]: it for it in body["items"]}


def test_the_status_rows_follow_the_language(lang):
    lang("zz")
    rows = _status_rows()
    assert rows["llm"]["label"] == "Fast brain · FlashBrain"
    assert rows["memory"]["label"] == "Memory · HEART"
    assert rows["stt"]["label"] == "STT · speech→text" and rows["tts"]["label"] == "TTS · text→speech"
    assert "online · port" in rows["server"]["detail"]
    spoken = " ".join(f"{r.get('label', '')} {r.get('detail', '')}" for r in rows.values())
    for castilian in ("Servidor", "Cerebro", "Memoria", "Sistema de voz", "en línea", "sin clusters", "eventos"):
        assert castilian not in spoken, f"{castilian!r} leaked into a non-Spanish status: {spoken}"
    lang("es")
    rows = _status_rows()
    assert rows["llm"]["label"] == "Cerebro rápido · FlashBrain"
    assert rows["memory"]["label"] == "Memoria · CORAZÓN"
    assert "en línea · puerto" in rows["server"]["detail"]


def test_a_balance_line_follows_the_language(lang, monkeypatch):
    import voice
    from config import balances

    class _HS:
        @staticmethod
        def get(k):
            return {"kind": "credit", "text": "429"} if k == "llm" else None
    monkeypatch.setitem(sys.modules, "voice.health_state", _HS)
    monkeypatch.setattr(voice, "health_state", _HS, raising=False)
    monkeypatch.setattr("config.doctor.credentials",
                        lambda: [{"key": "deepseek", "enables": "LLM", "profiles": [], "env": ["DEEPSEEK_API_KEY"], "set": True}])
    lang("zz")
    assert balances.summary()[0]["detail"] == "NO BALANCE/quota"
    assert "MEASURED" in balances._zai_credits_verdict(200, "")["detail"]
    lang("es")
    assert balances.summary()[0]["detail"] == "SIN SALDO/cuota"
    assert "MEDIDO" in balances._zai_credits_verdict(200, "")["detail"]


def test_the_voice_knobs_follow_the_language(lang):
    from config import settings
    lang("zz")
    knobs = {k["key"]: k for k in settings.effective()["knobs"]}
    assert knobs["stt_language"]["label"] == "Language"
    assert "Push to talk" in [o["label"] for o in knobs["attention_mode"]["options"]]
    lang("es")
    knobs = {k["key"]: k for k in settings.effective()["knobs"]}
    assert knobs["stt_language"]["label"] == "Idioma"
    assert "Pulsar para hablar" in [o["label"] for o in knobs["attention_mode"]["options"]]


def test_the_provider_catalog_and_the_benchmarks_follow_the_language(lang):
    from config import model_benchmarks
    from server import config_api
    lang("zz")
    assert config_api._catalog_for_ui()["fast"]["note"].startswith("NON-reasoners only")
    assert model_benchmarks.snapshot()["modules"][0]["label"] == "Fast brain · FlashBrain"
    lang("es")
    assert config_api._catalog_for_ui()["fast"]["note"].startswith("Solo NO razonadores")
    assert model_benchmarks.snapshot()["modules"][0]["label"] == "Cerebro rápido · FlashBrain"
    assert config_api._PROVIDER_CATALOG["fast"]["note"].startswith("NON-reasoners only"), "the constant was mutated"


def test_every_key_these_surfaces_read_exists_in_both_presets():
    """A key that is read but never written would quietly show its English default in Spanish too."""
    en = json.loads((ENGINE / "i18n/genesis/en/ui.json").read_text(encoding="utf-8"))
    es = json.loads((ENGINE / "i18n/genesis/es/ui.json").read_text(encoding="utf-8"))
    keys = set()
    for rel in SOURCES:
        keys |= set(re.findall(r"""["']((?:status|statussvc|config)\.[a-z_]+\.[a-z_.]+)["']""",
                               (ENGINE / rel).read_text(encoding="utf-8")))
    keys = {k for k in keys if not k.endswith("_")}          # prefixes completed at runtime («cron_running_» + one/many)
    keys |= {f"status.detail.{p}_{n}" for p in ("cron_running", "widgets") for n in ("one", "many")}
    assert len(keys) > 60
    assert not sorted(k for k in keys if k not in en or k not in es)
