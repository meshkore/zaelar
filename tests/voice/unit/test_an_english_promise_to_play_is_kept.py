"""An ENGLISH promise of playback is kept by the music backstop (demo passes 34-51, 2026-09-29, U2).

«no, put like a prayer» → «Sure — putting on Like a Prayer now.» and no tool, nine turns of twenty-one. The promise
backstop only knew the Spanish forms («voy a poner algo de rock»), the act-repair door needs a card the catalogue
names (it answered `none` with the music card open), so the reply stood alone. The grammar below reads the promise,
gated on the music card being open or a music word in the turn, and takes the TITLE from the words — never the
operator's whole sentence as a search. Both channels are wired (the provider and its probe mirror).
"""
from __future__ import annotations

from tests import voice_turn_source as _vts

from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize("reply,operator,music_open", [
    ("Sure — putting on Like a Prayer now.", "no, put like a prayer", True),
    ("Yep, switching it — Like a Prayer coming up.", "no, put like a prayer", True),
    ("Switching it to Like a Prayer.", "no, put like a prayer", True),
    ("Yeah… putting on Like a Prayer.", "no, put like a prayer", True),
    ("Right — like a prayer it is.", "no, put like a prayer", True),
    ("There you go — Like a Prayer.", "no, put like a prayer", True),
    ("Sure, putting on some Madonna.", "play some madonna", False),   # no card yet, but «play some …» is music
    ("Playing some Madonna now.", "play some madonna music", False),
])
def test_an_english_promise_of_playback_is_read(reply, operator, music_open):
    from nucleo.flash import playback_promise as rg
    assert rg.promises_playback(reply, operator, music_open=music_open)


@pytest.mark.parametrize("reply,operator,music_open", [
    ("Yep — playing number five now.", "put on number five", False),          # the video card, not a song
    ("Bringing up the Washington Examiner piece on Starship now.", "play the second one", False),
    ("Back to normal size.", "ok that's enough, go back to normal size", True),
    ("Paused.", "pause it a sec", True),
    ("I'll find them for you now.", "show me some videos of the spacex starship tests", False),
    ("There you go.", "what's on my plate tomorrow", True),                   # a claim, but no order to play
])
def test_a_reply_that_promises_no_playback_is_left_alone(reply, operator, music_open):
    from nucleo.flash import playback_promise as rg
    assert not rg.promises_playback(reply, operator, music_open=music_open)


@pytest.mark.parametrize("reply,operator,query", [
    ("Sure — putting on Like a Prayer now.", "no, put like a prayer", "Like a Prayer"),
    ("Yep, switching it — Like a Prayer coming up.", "no, put like a prayer", "Like a Prayer"),
    ("Switching it to Like a Prayer.", "no, put like a prayer", "Like a Prayer"),
    ("Right — like a prayer it is.", "no, put like a prayer", "like a prayer"),
    ("There you go — Like a Prayer.", "no, put like a prayer", "like a prayer"),
    ("Sure, putting on some Madonna.", "play some madonna", "Madonna"),
    ("Playing some Madonna now.", "play some madonna", "Madonna"),
    ("Putting it on for you.", "yeah, can you play like a prayer by madonna", "like a prayer by madonna"),
])
def test_the_query_is_the_title_the_words_carry(reply, operator, query):
    from nucleo.flash import playback_promise as rg
    assert rg.music_query(reply, operator) == query


def test_both_channels_play_an_english_promise_before_any_worker():
    """The provider's branch runs BEFORE the escalate/show branches (a song is on the player, not on the web) and
    the probe mirrors it; both take the query from `music_query`, never the sentence whole."""
    prov = _vts.read(ENGINE / "voice/engine/llm/providers/nucleo.py")
    assert 'promises_playback(spoken_text, _op_text, music_open=_direct_action.on_screen_now("musica"))' in prov
    head, tail = prov.split("elif _playback:", 1)
    assert 'emit("brain", "🪟 show por backstop de promesa' in head
    assert "elif (_router.looks_like_create_widget(_op_text) or _router.looks_like_escalate_task(_op_text)" in tail
    assert 'music_req["v"] = {"query": _router.music_query(spoken_text, _op_text), "action": "play"}' in tail
    probe = (ENGINE / "nucleo/flash/probe.py").read_text(encoding="utf-8")
    assert 'promises_playback(spoken, text, music_open=' in probe
    assert 'music_req = {"action": "play", "query": _routerc.music_query(spoken, text)}' in probe
