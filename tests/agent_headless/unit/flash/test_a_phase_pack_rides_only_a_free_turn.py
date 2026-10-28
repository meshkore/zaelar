"""A phase pack rides only a FREE turn — a question or an order gets its answer, not our introduction (V2-781).

ES round 2026-10-11, t10: «…¿Sigo con algo o le damos a la agenda?» → «Una cosa antes de nada: ¿cómo te llamas? Y si
quieres te cuento en un momento qué puedo hacer por ti.» EN: «did you turn down the music or the video?» → «…By the
way, I don't think I've caught your name yet.»; «pause the video.» → «…Meanwhile, Alex, where are you based?». The
introduction pack said in prose «solve his request first»; the model did not. Now `packs.compose(turn_text)`
sends no pack at all unless `free_turn.is_free` — no question mark, no order verb, a short sentence.
"""
from __future__ import annotations

import pytest

from nucleo.turn.prompt import packs as CP
from nucleo.turn.prompt.packs import free_turn as F

@pytest.mark.parametrize("text,why", [
    ("Perfecto, música cerrada. Te quedan el tráiler pausado y la agenda abierta. ¿Sigo con algo o le damos a la agenda?",
     "question"),
    ("hey, did you turn down the music or the video?", "question"),
    ("got it, thanks. pause the video.", "order"),
    ("Alex. And pause that for a sec.", "order"),
    ("Ponme el tráiler de Dune, y de fondo algo de música tranquila.", "order"),
    ("No importa eso. Mira la agenda, que sigo con el tráiler pausado.", "order"),
    ("ayer estuve con mi hermana en el cine y luego cenamos por el centro con unos amigos suyos que yo no conocía",
     "long"),
])
def test_a_question_an_order_or_a_long_sentence_is_not_free(text, why):
    assert F.why_not(text) == why, (text, F.why_not(text))
    assert not F.is_free(text)


@pytest.mark.parametrize("text", ["Alex", "me llamo Alex, encantado", "hola, buenos días", "vale, gracias",
                                  "I'm in Lisbon", "es para mi madre", ""])
def test_a_greeting_an_answer_or_a_short_remark_is_free(text):
    assert F.is_free(text), (text, F.why_not(text))


@pytest.fixture
def one_pack(monkeypatch):
    pack = CP.Pack(id="t", title="t", order=1, active=lambda: True, block=lambda: "ASK HIS NAME")
    monkeypatch.setattr(CP, "_REGISTRY", [pack])
    return pack


def test_compose_sends_nothing_on_a_question_or_an_order(one_pack):
    assert CP.compose("¿Sigo con algo o le damos a la agenda?") == ""
    assert CP.compose("pause the video.") == ""


def test_compose_still_sends_the_pack_on_a_free_turn(one_pack):
    assert "ASK HIS NAME" in CP.compose("hola, buenos días")
    assert "ASK HIS NAME" in CP.compose()          # callers without a turn text keep today's behaviour


def test_the_built_prompt_carries_the_pack_only_on_a_free_turn(one_pack, monkeypatch):
    """By behaviour, on the prompt the model reads (refactor2710-08 rewrote the source read): the builder hands the
    turn's text to the packs, so the same engine sends the pack on «hola» and withholds it on a question."""
    from nucleo.flash import memory_cache
    from nucleo.turn.prompt import builder as prompt
    monkeypatch.setattr(memory_cache, "get", lambda: ("", ""))
    assert "ASK HIS NAME" in prompt.build_flash_system(turn_text="hola, buenos días")[0]
    assert "ASK HIS NAME" not in prompt.build_flash_system(turn_text="¿Sigo con algo o le damos a la agenda?")[0]
