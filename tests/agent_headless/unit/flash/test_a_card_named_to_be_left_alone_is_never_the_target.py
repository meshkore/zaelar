"""A card his sentence names only to be LEFT ALONE is never the target of a shared control (V2-781, ES round 2026-10-11).

`tres-tarjetas-y-el-video-por-alusion`: the Dune trailer on `youtube`, calm music on `musica`, both declaring
`volume_down`. «La música, la de fondo. El YouTube déjalo como está» / «No, en YouTube no: bájale a la música, el vídeo
no lo toques» / «…no es YouTube, es la música de fondo…» ran `youtube.volume_down` three turns in a row: the catalogue's
best match for the sentence was the brand name, and `acts.media` took it as the player he named. One reader now
splits a sentence into the cards it targets and the cards it excludes (keep clause, don't-touch, a negation next to the
name) — `named_target` — and `which_card`, `acts.media` and `undecided` all ask it before any verdict.
"""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nucleo.acts import named_target as NT

ENGINE = Path(__file__).resolve().parents[4]
THREE = ["youtube", "musica", "agenda"]


def _brief(screen: str = "", conf: float = 0.5, open_ids=THREE) -> dict:
    ev = threading.Event()
    ev.set()
    res = {"screen_action": {"choice": screen, "confidence": conf}} if screen else {}
    return {"event": ev, "turn_id": "t-1", "open_ids": list(open_ids), "result": res}


@pytest.fixture
def screen(monkeypatch):
    import server.voice_api as _va
    from memory import api as _memapi
    monkeypatch.setattr(_va, "open_instances", lambda: list(THREE))
    monkeypatch.setattr(_memapi, "state", lambda *a, **k: {"open_widgets": list(THREE)})
    monkeypatch.setattr(_memapi, "kv_get", lambda k, *a, **kw: None)
    from nucleo import canvas_focus
    monkeypatch.setattr(canvas_focus, "last_turn_card", lambda ids: "")


# ── the reader ─────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "El de la música, el vídeo déjalo.",
    "La música, la de fondo. El YouTube déjalo como está.",
    "No, en YouTube no: bájale a la música, el vídeo no lo toques.",
    "Oye, que no es YouTube, es la música de fondo. Bájale a la música y el vídeo no lo toques, porfa.",
    "A ver, no: la música de fondo, no YouTube. Bájale a la música y el vídeo déjalo.",
    "the music, not the video",
    "turn the music down, leave the video alone",
])
def test_the_music_is_the_target_and_the_video_is_excluded(text):
    targets, excluded = NT.split(text, THREE)
    assert targets == ["musica"] and excluded == ["youtube"], (text, targets, excluded)
    assert NT.target(text, THREE, "volume_down") == "musica"


@pytest.mark.parametrize("text", [
    "The video, the trailer. Leave the music.",
    "Sorry, the YouTube one — the trailer. Pause that, keep the music going.",
    "la música no, el vídeo",
    "no bajes la música, baja el vídeo",
])
def test_the_video_is_the_target_when_the_music_is_the_one_left_alone(text):
    assert NT.target(text, THREE, "pause") == "youtube", (text, NT.split(text, THREE))


def test_nothing_named_or_two_named_decides_nothing():
    assert NT.target("Turn the volume down.", THREE, "volume_down") == ""
    assert NT.target("pausa la música y el vídeo", THREE, "pause") == ""


def test_a_negation_far_from_the_name_is_a_request_not_a_denial():
    assert NT.target("¿no puedes bajar la música?", THREE, "volume_down") == "musica"
    assert NT.target("no quiero que suene tan alto la música", THREE, "volume_down") == "musica"


def test_the_only_card_left_once_the_denied_one_is_out_is_the_target():
    assert NT.target("not YouTube", ["youtube", "musica"], "volume_down") == "musica"
    assert NT.target("not YouTube", THREE, "show") == ""          # two others declare `show`: nothing decided


def test_a_dont_touch_with_a_clitic_is_a_keep_clause():
    from widgets import naming
    assert "vídeo" in naming.split_kept("bájale a la música, el vídeo no lo toques")[1]
    assert "video" in naming.split_kept("turn the music down, don't touch the video")[1]


# ── the sites that ask it ──────────────────────────────────────────────────────────────────────────────────────

def test_which_card_takes_the_named_target_over_a_none_or_wrong_verdict(screen):
    from nucleo.flash import frontend as FE
    text = "La música, la de fondo. El YouTube déjalo como está."
    assert FE.which_card("youtube", "volume_down", brief=_brief("none", 0.58), operator_text=text) == ("card", "musica")
    assert FE.which_card("youtube", "volume_down", brief=_brief("youtube:volume_down", 0.95), operator_text=text) \
        == ("card", "musica")
    assert FE.which_card("musica", "volume_down", brief=_brief("youtube:volume_down", 0.95), operator_text=text)[0] == "keep"
    assert FE.which_card("youtube", "volume_down", brief=_brief("none", 0.58))[0] == "ask"    # no words: today's path


def test_the_player_tool_moves_to_the_named_player_never_to_the_excluded_one(screen):
    from nucleo.acts import media as PC
    for text in ("La música, la de fondo. El YouTube déjalo como está.",
                 "No, en YouTube no: bájale a la música, el vídeo no lo toques."):
        p = PC.plan("play_music", "volume_down", "", brief=_brief("none", 0.58), operator_text=text)
        assert p["route"] == "keep" and p["card"] == "musica", (text, p)
    p = PC.plan("play_music", "pause", "", brief=_brief("", 0.0), operator_text="The video, the trailer. Leave the music.")
    assert p["route"] == "card" and p["card"] == "youtube", p


def test_the_rung_runs_the_named_card_and_never_the_excluded_one(screen):
    from nucleo.flash import undecided as U
    text = "No, en YouTube no: bájale a la música, el vídeo no lo toques."
    assert U.why(_brief("musica:volume_down", 0.6), "musica", "volume_down", operator_text=text) == ""
    assert U.why(_brief("youtube:volume_down", 0.6), "youtube", "volume_down", operator_text=text) == "shared"


def test_the_voice_turn_hands_his_words_to_the_card_decision():
    voice = (ENGINE / "nucleo/flash/tool_executor_widget_calls.py").read_text(encoding="utf-8")
    assert "payload=payload, operator_text=_txw._bnotes.operator_half(text))" in voice
