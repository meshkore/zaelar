"""Node 2.598 — a reply never claims it checked whether a video is AI-made: nothing in the engine can.

`find-videos-on-a-topic-no-ai-slop` (2026-10-14). ES t0: «…filtrando los que huelen a generado» — no filter ran. EN
t2, a chat turn with no op at all: «a real person filming in his own garden, no synthetic voice». A search row is
title, channel and date; no card returns provenance. The sentence that claims the check is dropped and the honest
caveat is said instead (text channel); the voice, whose words have streamed, says the caveat after them.

Disarm: `_claims` returning False → the first two tests go red; either wire removed → the wiring test goes red.
"""
from __future__ import annotations

from pathlib import Path

from i18n import langs
from nucleo.flash import unchecked_provenance as UP

ENGINE = Path(__file__).resolve().parents[4]
ES0 = ("Busco vídeos de poda de olivo y te los dejo para elegir, filtrando los que huelen a generado. Tienes 6 "
       "resultados en el Inicio del reproductor: «Curso Completo para PODAR CORRECTAMENTE un OLIVO!! Fácil» y 5 más.")
EN2 = ("Right — the other three are «How to Prune an Olive Tree» by The Palm Centre. On the emojis one: the channel "
       "is The Frenchie Gardener — a real person filming in his own garden, no synthetic voice, so it's probably the "
       "emoji. Want me to play the Palm Centre one?")


def test_the_claimed_filter_is_dropped_and_the_caveat_said_in_spanish():
    es = langs.spec("es")
    out = UP.honest(ES0, es, video=True)
    assert "filtrando" not in out and "Tienes 6 resultados" in out and "PODAR CORRECTAMENTE un OLIVO!!" in out
    assert out.endswith(es.provenance_unchecked)


def test_the_claimed_check_is_dropped_in_english_and_the_voice_owes_the_caveat():
    en = langs.spec("en")
    out = UP.honest(EN2, en, video=True)
    assert "synthetic" not in out and "real person" not in out and "Palm Centre one?" in out
    assert UP.voice_owed(EN2, en, video=True) == en.provenance_unchecked


def test_honest_replies_and_other_cards_are_untouched():
    en = langs.spec("en")
    for clean in ("I can't check whether a video is AI-made: I only see titles and channels.",
                  "Playing «How to Prune an Olive Tree» now.", "The queue now has 3."):
        assert UP.honest(clean, en, video=True) == clean and UP.voice_owed(clean, en, video=True) == ""
    assert UP.honest(EN2, en, video=False) == EN2, "only over the video player"


def test_the_voice_turn_asks_it():
    voice = (ENGINE / "nucleo/flash/post_stream_settle.py").read_text("utf-8")
    assert "_pst_up.said_after(_pst_fsn.said_after(spoken_text, send, speech), send, speech)" in voice and "spoken_text = " in voice   # row claims wrap it (2.690)
