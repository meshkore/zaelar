"""A song title is a NAME, so every music line of ours quotes it, in both languages (node 2.909).

play-music-and-build-playlist ES (2026-10-28): «Suena Make you feel positive and peaceful 🍀 Lofi Coffee…» was filed as
an English reply. The words around the title were Spanish; the title was bare, so its English outvoted them. Every
other line that names something of his already quotes it («No he encontrado «{q}»», «Suena ahora «{title}»»). The
same applied to a missing title: the fallback was the Spanish literal «la música», spoken in every language.

Disarm: drop the «» around `{label}` in the es `play` template and the first test goes red.
"""
from __future__ import annotations

import pytest

from i18n import langs
from tests.use_cases.e2e.agent.gates import reply_language

TITLE = "Make you feel positive and peaceful Lofi Coffee ~ Lofi Hip Hop - Lofi Music"
KEYS = ("music.youtube.play", "music.youtube.already", "music.youtube.queued", "music.spotify.play",
        "music.spotify.play_on", "music.spotify.already_on")


@pytest.mark.parametrize("code", ["es", "en"])
def test_a_line_naming_an_english_title_speaks_the_sessions_language(monkeypatch, code):
    monkeypatch.setattr(langs, "current_code", lambda: code)
    for key in KEYS:
        line = langs.words(key, default="").format(label=TITLE, device="Salón", n=1)
        assert f"«{TITLE}»" in line, (key, line)
        assert reply_language(line, code) in (code, ""), (key, line)


@pytest.mark.parametrize("code,foreign", [("es", "music"), ("en", "música")])
def test_a_play_with_no_title_has_no_word_of_the_other_language(monkeypatch, code, foreign):
    from connectors.music import youtube_audio as ya
    monkeypatch.setattr(langs, "current_code", lambda: code)
    line = ya._t("play_untitled")
    assert line and foreign not in line.lower(), line
