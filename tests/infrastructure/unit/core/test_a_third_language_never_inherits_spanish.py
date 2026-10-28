"""A third language never inherits Spanish (V2-778 — every human word lives in `i18n/genesis/<code>/voice.json`).

The tables these surfaces used to carry were `{"es": …, "en": …}` with Spanish as the fallback, or a binary
`en if … else es` ternary: an agent onboarded in French said its music, agenda, reminder and search lines in
Spanish without any error. Now each surface reads `langs.words(...)` — the active language, then English. This
pins both halves: with «fr» active and NO generated French pack, every surface speaks English; with «es», the
Castilian sentences of always.
"""
from __future__ import annotations

import pytest


def _speak(monkeypatch, code: str):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    monkeypatch.setitem(langs._WORDS, "fr", {})          # «fr» has no generated pack, whatever this disk holds


def _music_seam():
    import connectors.music as M
    return M._msg("no_provider")


def _youtube_audio():
    from connectors.music import youtube_audio as Y
    return Y._t("play", label="X")


def _spotify():
    import importlib
    return importlib.import_module("connectors.spotify.provider")._t("not_connected")


def _planner():
    from i18n import langs
    from widgets.agenda import planner
    return planner._lbl(langs.current_code())["summary"]


def _recur():
    from i18n import langs
    from widgets.agenda import recur
    return recur.describe({"freq": "weekly", "days": [0, 1], "interval": 1}, langs.current_code())


def _origin_label():
    from search.result import Candidate
    return Candidate(title="T", origin="web").to_row()["facts"][0]


def _song_hint():
    from i18n import langs
    return langs.words("hints.song_many").format(n=2)


def _youtube_notice():
    from widgets.youtube import availability
    return availability.tell_for({"blocked_notice": {"kind": "explicit", "from": "V"}})


def _blocked_channel():
    from widgets.youtube import data  # noqa: F401 — the card's module first: `blocking` is imported through it
    from widgets.youtube import blocking
    return blocking._say("already", ch="C")


SURFACES = [
    (_music_seam, "I don't have a music account", "No tengo ninguna cuenta de música"),
    (_youtube_audio, "Now playing X.", "Suena X."),
    (_spotify, "Connect your Spotify account first", "Necesito que conectes tu cuenta de Spotify"),
    (_planner, "{n} tasks planned", "{n} tareas planificadas"),
    (_recur, "every Mondays and Tuesdays (no end date)", "todos los lunes y martes (sin fecha de fin)"),
    (_origin_label, {"label": "Origin", "value": "web search"}, {"label": "Origen", "value": "búsqueda web"}),
    (_song_hint, "2 songs", "2 canciones"),
    (_youtube_notice, "«V» can't be played here", "«V» no se puede reproducir aquí"),
    (_blocked_channel, "«C» was already blocked.", "«C» ya estaba bloqueado."),
]


def _has(got, want) -> bool:
    return got == want if isinstance(want, dict) else want in got


@pytest.mark.parametrize("surface, en, es", SURFACES, ids=[s[0].__name__.strip("_") for s in SURFACES])
def test_a_language_without_its_own_words_speaks_english(monkeypatch, surface, en, es):
    _speak(monkeypatch, "fr")
    got = surface()
    assert _has(got, en), f"«fr» with no pack must fall back to ENGLISH, got {got!r}"


@pytest.mark.parametrize("surface, en, es", SURFACES, ids=[s[0].__name__.strip("_") for s in SURFACES])
def test_spanish_keeps_its_own_sentences(monkeypatch, surface, en, es):
    _speak(monkeypatch, "es")
    got = surface()
    assert _has(got, es), got


def test_the_horizon_labels_follow_the_language(monkeypatch):
    from widgets.agenda import data as AD
    _speak(monkeypatch, "fr")
    days = AD._horizon({"user": {}, "projects": [], "tasks": [], "meetings": []}, span=2)
    assert [d["label"] for d in days] == ["Today", "Tomorrow"]
    _speak(monkeypatch, "es")
    days = AD._horizon({"user": {}, "projects": [], "tasks": [], "meetings": []}, span=2)
    assert [d["label"] for d in days] == ["Hoy", "Mañana"]


def test_an_unreadable_language_locale_is_english_not_spanish(monkeypatch):
    """Locale codes are not words, but their fallback followed the same Spanish default."""
    from i18n import langs
    from search import web
    from widgets.navegador import launch_env
    for k in ("NAVEGADOR_LOCALE", "NAVEGADOR_TZ"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(langs, "current_code", lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert web._accept_language().startswith("en-US")
    assert launch_env._browser_locale()[0] == "en-US"
