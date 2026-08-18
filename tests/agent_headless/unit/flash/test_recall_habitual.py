"""V2-130 — a definite reference to a habitual thing is a memory question in disguise.

`book-barber-slot__es` opened with «Resérvame hora en la peluquería de siempre para el sábado por la mañana»
and `needs_recall` returned False, so the semantic prefetch never ran: the brain answered about the operator's
usual hairdresser having never looked for it. Measured over the transcript's own phrasings, 6 of 7 returned
False, and the one that returned True did so by accident (it happened to be phrased as a question).

The classifier was shaped by GRAMMAR — a question, or a recall imperative — while the signal here is SEMANTIC:
an ORDER is the natural way to say it, and an order never fired the prefetch.
"""
import pytest

from nucleo.flash import prompt


@pytest.mark.parametrize("text", [
    # The transcript's own turns, verbatim.
    "Resérvame hora en la peluquería de siempre para el sábado por la mañana.",
    "La de siempre, y temprano mejor.",
    # Same class, other phrasings — an order, never a question.
    "Pide lo de siempre en el chino",
    "llama a mi peluquería habitual",
    "reserva en mi restaurante de siempre",
    "hazlo como siempre",
    # Possessive + service provider: only memory knows which one.
    "renueva mi cuota del gimnasio",
    "recoge la receta de mi farmacia",
    "pide cita con mi dentista",
    "lleva el coche a mi taller",
    "book me a slot at my usual barber",
])
def test_a_habitual_reference_fires_the_recall_prefetch(text):
    assert prompt.needs_recall(text) is True


@pytest.mark.parametrize("text", [
    "hola",
    "vale",
    "gracias",
    "pon música",
    "sube el volumen",
    "apaga la luz",
    "¿me pones el tiempo en pantalla?",
])
def test_small_talk_and_device_commands_still_do_not(text):
    assert prompt.needs_recall(text) is False
