"""A health alert he can read is said in HIS language (V2-831 audit A15).

The class: the self watchdog (T-28), the voice-lag reader (T-30) and the worker envelope (T-27) each emitted an `alert`
— a line on his wall — as a Spanish literal, whatever language the session spoke. The lines are the voice pack's
`alerts.*` now (English the source, Spanish the preset, generated at init for any other language).
"""
from __future__ import annotations

import pytest


@pytest.mark.parametrize("code", ["en", "es"])
def test_the_self_watchdogs_alert_is_his_languages(monkeypatch, code):
    from i18n import langs
    from nucleo.pulse import self_watchdog
    from voice import observer
    monkeypatch.setattr(langs, "current_code", lambda: code)
    got: list = []
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: got.append((kind, label)))
    self_watchdog._emit("engine_shedding", loop_age_s=20.0)
    assert got == [("alert", langs.words("alerts.engine_shedding", code=code))]


def test_every_alert_exists_in_both_product_languages():
    from i18n import langs
    en, es = langs.words("alerts", code="en"), langs.words("alerts", code="es")
    assert set(en) == set(es) and all(en.values()) and all(es.values())
    assert en != es

