"""A failed music act is worded by the turn from its FACTS — never a canned «tell me the artist» after «te la pongo»
(V2-833 F3).

Measured 2026-11-01 on a hosted engine: ten times the model said «te la pongo» and the engine appended the connector's
canned «No he dado con esa canción. ¿Me dices el artista…?», while the cause was ours (the catalogue lookup came back
empty without saying why) and Spotify was connected. The class: an act's outcome reached him as a canned line that
blamed his input. Now the lookup's own outcome travels (`unreachable` is never `no_track`), an unreachable catalogue
skips the web-resolution chain (it cannot help), and the turn's follow-up pass words the facts — SKIP when what was
said still holds — with instructions that are language data in both product languages.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nucleo.flash import music_outcome


def _res(reason: str, **extra):
    return SimpleNamespace(ok=False, reason=reason, provider="youtube", extra=extra, message="canned")


@pytest.mark.parametrize("code", ["en", "es"])
@pytest.mark.parametrize("reason,option,absent", [("unreachable", "retry", "more_words"), ("no_track", "more_words", "retry")])
def test_the_facts_say_why_and_offer_only_what_fits(monkeypatch, code, reason, option, absent):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    w = langs.words("music", code=code)
    sys2 = music_outcome.system("LOCK", "pon pa tipos como tú de Shakira", "Te la pongo.", _res(reason, tried="Shakira - Pa tipos como tú"))
    assert w["outcome_reasons"][reason] in sys2 and w["outcome_options"][option] in sys2
    assert w["outcome_options"][absent] not in sys2, "an option that does not fit this outcome was offered"
    assert "«Shakira - Pa tipos como tú»" in sys2 and sys2.startswith("LOCK")


def test_with_words_out_the_pass_runs_detached_and_nothing_canned_is_sent(monkeypatch):
    from nucleo.flash import follow_up_pass
    seen, sent = {}, []
    monkeypatch.setattr(follow_up_pass, "detach", lambda sys2, user, said, spec, mt, what, emit: seen.update(sys2=sys2, said=said) or True)
    out = asyncio.run(music_outcome.say(lang_lock="", asked="play x", said="Playing it now.", res=_res("unreachable"),
                                        spec=None, emit=lambda *a, **k: None, send=sent.append,
                                        speech=SimpleNamespace(sanitize=lambda s, **k: s)))
    assert out == "" and sent == [] and seen["said"] == "Playing it now."


@pytest.mark.parametrize("model,expected", [("SKIP", []), ("I couldn't reach the music catalogue right now.", ["I couldn't reach the music catalogue right now."])])
def test_with_nothing_said_the_pass_is_the_answer(monkeypatch, model, expected):
    from nucleo.flash import follow_up_pass

    async def _stream(client, sys2, user, spec, mt, what):
        yield model
    monkeypatch.setattr(follow_up_pass, "detach", lambda *a, **k: False)
    monkeypatch.setattr(follow_up_pass, "measured", _stream)
    sent: list = []
    asyncio.run(music_outcome.say(lang_lock="", asked="play x", said="", res=_res("unreachable"), spec=None,
                                  emit=lambda *a, **k: None, send=sent.append, speech=SimpleNamespace(sanitize=lambda s, **k: s)))
    assert sent == expected


def test_an_unreachable_catalogue_is_never_no_such_song_and_skips_the_web_chain(monkeypatch, tmp_path):
    import widgets.store as store
    from connectors import music
    from connectors.music import registry, youtube_audio as yta
    from nucleo.flash import music_flow
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(yta, "_resolve", lambda q: ("", "", "unreachable"))
    registry._PROVIDERS.clear()
    registry._loaded = True
    registry.register(yta.YouTubeAudioProvider())
    asked: list = []

    async def _extract(sys2, user2):
        asked.append(user2)
        return "Shakira - Pa tipos como tú"
    try:
        res = asyncio.run(music_flow.run("play", "pa tipos como tú", extract=_extract))
    finally:
        registry._PROVIDERS.clear()
        registry._loaded = False
    assert res.reason == "unreachable" and asked == [], "the web chain ran for a catalogue that could not be reached"
    assert music.control is not None
