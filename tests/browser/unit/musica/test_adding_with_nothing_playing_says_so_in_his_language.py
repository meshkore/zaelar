"""«Add it to my Work list» with nothing playing and no song named is told AS that, in his language.

`add_to_playlist` refused with a hard-coded Spanish `message` («No suena nada ahora y no me has dicho qué canción
añadir.»), so an English session heard Spanish or — after `refusal_line` cut the foreign line — the generic «the
Music card didn't take it». The refusal now carries a bundle key (`say`), like `favorite_current` (node 2.561), and
still creates no empty list.

Disarm: put the Spanish `message` back instead of `say` and the English case goes red.
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
    res = md.apply_action("add_to_playlist", {"playlist": "Work"})
    assert res["ok"] is False and res["error"] == "nothing_playing"
    line = RL.speakable("musica", res)
    assert word in line.lower() and line != RL.generic("musica")
    assert md._load_db()["playlists"] == [], "a refused save leaves no empty list behind"
