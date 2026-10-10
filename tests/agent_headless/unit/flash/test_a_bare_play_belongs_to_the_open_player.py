"""A bare play order or «what is playing?» belongs to the player on screen, not the closed one (V2-781).

Measured in `build-a-video-playlist-from-links` (ES, 2026-10-10, probe channel). The list «la de la tarde» was built
and named on the open `youtube` card, the music card was closed, and he said «Dale, ¿y qué está sonando ahora?». The
model only promised to check; the screen verdict read a sure «none»; `card_commission.named_or_catalogue` then asked
the catalogue — which describes CLOSED cards and cannot see that a video list is on screen — and got `musica` (0.98).
The repair pass, offered the music card, invented `musica:play_playlist {"playlist": "Favoritos"}`, and the turn said
«No he podido: No encuentro ninguna lista que se llame «Favoritos»».

Two bounds, both driven through the real functions:
  · the late catalogue naming a CLOSED player while ANOTHER player is open hands the order to the open one — unless
    his words name a card. The neighbourhood is measured: music open and no video → music; both closed → whatever
    the catalogue said; «ponme música» / «pon el vídeo de gatos» keep their own card.
  · a repaired call may not SELECT a named list nobody said and the card does not hold.
"""
from __future__ import annotations

import threading

import pytest

from nucleo import jev
from nucleo.flash import build_decision, card_commission as cc, player_control as pc, repair_grounding as rg
from nucleo.flash import turn_brief as tb

PLAY_ES = "Dale, ¿y qué está sonando ahora?"


@pytest.fixture
def late(monkeypatch):
    """`named_or_catalogue` with the brief of the measured turn: a sure «none» on screen, then the catalogue."""
    monkeypatch.setattr(build_decision, "named_card", lambda brief: "")
    monkeypatch.setattr(tb, "catalog_question", lambda: {"instructions": "i", "criteria": {"musica": "m"}})

    def _ask(text, *, catalogue, open_ids):
        monkeypatch.setattr(jev, "choose_sync", lambda *a, **k: {"choice": catalogue, "confidence": 0.98})
        ev = threading.Event()
        ev.set()
        brief = {"event": ev, "turn_id": "t", "open_ids": list(open_ids),
                 "result": {tb.TARGET_KEY: {"choice": "none", "confidence": 0.99}}}
        return cc.named_or_catalogue(brief, text)
    return _ask


@pytest.mark.parametrize("text", [PLAY_ES, "Vale, perfecto. Ponla ya y dime qué está sonando.", "dale al play",
                                  "play it and tell me what's playing"])
def test_the_open_video_list_owns_a_bare_play(late, text):
    assert late(text, catalogue="musica", open_ids=["youtube"]) == "youtube"


def test_with_the_music_open_and_no_video_it_stays_music(late):
    assert late(PLAY_ES, catalogue="musica", open_ids=["musica"]) == "musica"


def test_the_mirror_a_closed_video_named_over_open_music_goes_to_the_music(late):
    assert late("dale al play", catalogue="youtube", open_ids=["musica"]) == "musica"


def test_with_no_player_open_the_catalogue_is_kept(late):
    assert late(PLAY_ES, catalogue="musica", open_ids=["agenda"]) == "musica"


@pytest.mark.parametrize("text,card", [("ponme música", "musica"), ("pon mi lista de spotify", "musica")])
def test_words_that_name_the_closed_card_keep_it(late, text, card):
    assert late(text, catalogue=card, open_ids=["youtube"]) == card


def test_a_video_named_over_open_music_keeps_the_video(late):
    assert late("pon el vídeo de gatos", catalogue="youtube", open_ids=["musica"]) == "youtube"


def test_a_card_that_is_not_a_player_is_never_moved():
    assert pc.open_player_owns("agenda", PLAY_ES, open_ids=["youtube"]) == "agenda"


def test_both_players_open_is_not_this_rule():
    # which of two OPEN players is `frontend.which_card`'s question; the catalogue named an open one
    assert pc.open_player_owns("musica", PLAY_ES, open_ids=["youtube", "musica"]) == "musica"


# ── the repaired call may not select a list nobody said ─────────────────────────────────────────────────────

def test_an_invented_list_name_is_refused():
    assert not rg.list_was_named({"playlist": "Favoritos"}, PLAY_ES,
                                 [{"role": "user", "content": "llámala 'la de la tarde'"}],
                                 "Todavía no hay ninguna lista guardada.")


def test_a_list_he_said_or_the_card_holds_passes():
    win = [{"role": "user", "content": "Perfecto, llámala 'la de la tarde'."}]
    assert rg.list_was_named({"list": "La de la Tarde"}, PLAY_ES, win)
    assert rg.list_was_named({"playlist": "Favoritos"}, "pon la lista", [], "Listas: «Favoritos» (12 canciones)")
    assert rg.list_was_named({"playlist": "favoritos"}, "pon mis Favoritos", [])
    assert rg.list_was_named({"query": "anything"}, PLAY_ES, [])


def test_the_repair_pass_drops_the_invented_list(monkeypatch):
    """`act_repair.call_for_promise` end to end with the model stubbed to return the measured call."""
    import asyncio

    from nucleo.flash import act_repair as ar
    from nucleo.flash import fast_client as fc
    from nucleo.flash import widget_read as wr

    monkeypatch.setattr(wr, "read", lambda wid: "Todavía no hay ninguna lista guardada.")

    async def _complete(self, messages, **kw):
        kw["on_tool_call"]("widget_data", {"widget_id": "musica", "action": "play_playlist",
                                           "payload": {"playlist": "Favoritos"}})
        return ""
    monkeypatch.setattr(fc.FastClient, "complete", _complete)
    got = asyncio.run(ar.call_for_promise(PLAY_ES, "Dame un segundo que compruebe lo que suena.", "musica",
                                          window=[{"role": "user", "content": "llámala 'la de la tarde'"}]))
    assert got is None
