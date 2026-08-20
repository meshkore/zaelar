"""V2-210 — a checkable fact about the world, answered with a figure and no source.

Measured on `quick-fact-opening-hours` (2026-08-20 15:08), the cleanest failure on the board because there is
nothing else in it — no wall, no worker, no network error:

    TESTER  ¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?
    ZAELAR  Mañana abre a las 10:00 y la entrada general cuesta 15 €.

Zero tools. Families observed: flash, memory, system — no `search` anywhere. The figures happen to be roughly
right, and that is exactly what makes it dangerous: the model is confident, so it never reaches for
`web_search`, and a confident wrong price reads exactly like a confident right one.

V2-022 established that this class of question is answered IN THE TURN from a real source, and V2-135 already
fixed the composing half of this very case. What was missing was the trigger for the turn where the model does
not ask.
"""
import pytest

from nucleo.flash import router_guards as g


def test_the_measured_turn_needs_a_source():
    assert g.answer_needs_a_source(
        "¿A qué hora abre mañana el Museo del Prado y cuánto cuesta la entrada general?",
        "Mañana abre a las 10:00 y la entrada general cuesta 15 €.")


def test_english_too():
    assert g.answer_needs_a_source("What time does the Prado open?", "It opens at 10:00.")


@pytest.mark.parametrize("q,a", [
    # The operator's OWN things are answered from memory or from their account, never from a search engine.
    ("¿A qué hora es mi cita del dentista?", "A las 17:00."),
    ("¿Cuánto cuesta mi seguro del coche?", "Son 420 € al año."),
    # No figure claimed → nothing to check, and forcing a search here spends a second on every vague sentence.
    ("¿A qué hora abre el Prado?", "Suele abrir por la mañana, pero lo miro y te digo."),
    # Not a question about the world at all. Arithmetic is full of digits and none of them are facts out there.
    ("¿Cuánto es 15 por 3?", "45."),
    # A number that is not a time or an amount is not a claim: «te lo digo en 2 minutos».
    ("¿Puedes mirarlo?", "Claro, te lo digo en 2 minutos."),
])
def test_what_must_NOT_fire(q, a):
    assert not g.answer_needs_a_source(q, a)


def test_an_empty_side_never_fires():
    assert not g.answer_needs_a_source("", "abre a las 10:00")
    assert not g.answer_needs_a_source("¿a qué hora abre el Prado?", "")


def test_the_probe_turns_it_into_a_real_search():
    """The half that makes it behaviour: the text channel must convert that turn into `search`, which is what
    reuses the machinery already there (V2-022 + the composing pass of V2-135). Asserted against the SOURCE of
    the turn, because the alternative is a live model call in a unit test — and a guard that is never wired is
    the failure mode this repo has paid for twice (Susurro, REM)."""
    import inspect

    from nucleo.flash import probe
    src = inspect.getsource(probe)
    assert "answer_needs_a_source" in src
    i = src.index("answer_needs_a_source")
    # …and that it actually flips the turn, not just consults the guard.
    assert 'action, _forced_search = "search", True' in src[i:i + 400]


def test_the_voice_channel_is_left_out_ON_PURPOSE_and_says_why():
    """This repo's rule is «impl PARALELA — cablear en AMBOS», so a channel left out has to be an argued
    decision and not an oversight: voice EMITS the model's deltas as they arrive, so by the time the turn could
    check, the improvised sentence has already been spoken. Adding the sourced version behind it means talking
    twice on every hours-or-price question."""
    import inspect

    from voice.engine.llm.providers import nucleo as vp
    src = inspect.getsource(vp)
    assert "V2-210" in src and "AQUÍ NO" in src
    assert "answer_needs_a_source(" not in src


def test_there_is_an_honest_line_when_the_source_cannot_be_reached():
    """With search down, keeping the original reply would leave exactly the improvised figure this exists to
    avoid. A «I couldn't check» is a worse answer and better information."""
    from voice.engine.core import langs
    for code in ("es", "en"):
        assert langs.spec(code).unverified_fact.strip()
