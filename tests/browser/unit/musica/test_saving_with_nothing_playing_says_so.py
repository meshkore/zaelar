"""«Save this song» with nothing playing is told AS that, in his language — not «the Music card didn't take it».

`music-save-what-is-sounding__us` (2026-10-11): three `favorite_current` calls were refused with `nothing_playing`,
an `error` with no `say` and no `message`, so `refusal_line` had nothing speakable and the operator heard the
generic «I couldn't: the Music card didn't take it.» three times — a technical failure, when the fact was that
nothing was sounding. The refusal now carries a bundle key, so the reason reaches him in either language.
"""
from __future__ import annotations

import pytest

from connectors.spotify import auth
from nucleo.flash import refusal_line as RL
from widgets.musica import data as md


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    import widgets.store as store
    monkeypatch.setattr(store, "_path", lambda wid: str(tmp_path / f"{wid}.json"))
    monkeypatch.setattr(store, "_legacy_path", lambda wid: str(tmp_path / f"{wid}_legacy.json"))
    monkeypatch.setattr(auth, "status", lambda: {"logged_in": False})


@pytest.mark.parametrize("code, word", [("en", "nothing is playing"), ("es", "no suena nada")])
def test_the_refusal_names_the_fact_in_the_session_language(monkeypatch, code, word):
    from i18n import langs
    monkeypatch.setattr(langs, "current_code", lambda: code)
    res = md.apply_action("favorite_current", {})
    assert res["ok"] is False and res["error"] == "nothing_playing"
    line = RL.speakable("musica", res)
    assert word in line.lower() and line != RL.generic("musica")


def test_with_a_song_sounding_it_saves_the_resolved_title():
    import widgets.store as store
    store.save("musica", {"yt": {"videoId": "FGBhQbmPwH8", "title": "Daft Punk - One More Time (Official Video)"}})
    assert md.apply_action("favorite_current", {})["ok"] is True
    fav = next(p for p in md._load_db()["playlists"] if p["name"] == "Favoritos")
    assert (fav["tracks"][0]["title"], fav["tracks"][0]["artist"]) == ("One More Time", "Daft Punk")
