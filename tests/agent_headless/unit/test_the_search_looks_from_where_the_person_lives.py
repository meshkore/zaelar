"""Twelve real New Orleans hotels, priced in euros, against a $150 budget.

Measured 2026-08-27 on the first US round of `find-best-hotel-city__us`. The candidates were right — Ritz
Carlton, Old No. 77, Courtyard by Marriott, all really in New Orleans — and unusable, because they came back
at €271 a night. It reads like a filtering bug and it is a GEOGRAPHY one: a site decides what currency and
which market to serve from the browser's locale and the `Accept-Language` header, not from the words of the
query. Both were pinned to Spain for every deployment, movable only by an env var nobody sets.

The site CATALOGUE was already locale-aware (`site_catalog`: OpenTable for the US, TheFork for Spain), so the
worker was being sent to the right American sites and then asking them in Spanish. Half a localisation is the
worse half: it looks like it works.

Both now follow the engine's own language, and the env vars still win — they are the escape hatch for an
engine whose language and country genuinely differ (an English speaker living in Madrid).
"""
from __future__ import annotations

import importlib


def _fresh(monkeypatch, module: str, lang: str, **env):
    for k in ("BROWSER_SEARCH_HL", "BROWSER_SEARCH_GL"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    return importlib.reload(importlib.import_module(module))


def test_an_english_engine_searches_from_the_us(monkeypatch):
    B = _fresh(monkeypatch, "nucleo.browser_search", "en")
    assert B._where() == ("en", "us")


def test_a_spanish_engine_keeps_searching_from_spain(monkeypatch):
    """The half that must not regress: this was the behaviour of always, and it was right for one deployment."""
    B = _fresh(monkeypatch, "nucleo.browser_search", "es")
    assert B._where() == ("es", "es")


def test_the_env_vars_still_win(monkeypatch):
    """An English speaker living in Madrid is a real person, and the language does not tell you the country."""
    B = _fresh(monkeypatch, "nucleo.browser_search", "en",
               BROWSER_SEARCH_HL="en", BROWSER_SEARCH_GL="es")
    assert B._where() == ("en", "es")


def test_the_web_search_header_follows_too(monkeypatch):
    """`Accept-Language` outranks the query: a Spanish header makes a US site answer in euros however the
    question was phrased."""
    W = _fresh(monkeypatch, "nucleo.websearch", "en")
    assert W._accept_language().startswith("en-US")
    W = _fresh(monkeypatch, "nucleo.websearch", "es")
    assert W._accept_language().startswith("es-ES")


def test_and_an_unreadable_language_falls_back_to_spanish_rather_than_dying(monkeypatch):
    """Fail-open, and in the direction of the behaviour of always: a search must never die because the
    language could not be read."""
    W = _fresh(monkeypatch, "nucleo.websearch", "es")
    monkeypatch.setattr("voice.engine.core.langs.current_code", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert W._accept_language().startswith("es-ES")
