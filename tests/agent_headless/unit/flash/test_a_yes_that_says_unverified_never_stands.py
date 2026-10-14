"""Node 2.688 — a «sí … sin verificar» never stands: it becomes «no lo tengo verificado».

search-buy-washing-machine__es (2026-10-14): «Sí, la Evvo Terra de 329 es de 8 kilos y clase A» with «…, sin
verificar» after it — a confirmation that un-confirms itself where he had asked for certainty. A yes and a «not
verified» in one sentence is repaired whether or not a row is named; quoting the words («nada de "sin confirmar"»)
is no contradiction, and a «not verified» without a yes is the honest sentence itself.

Disarm: `claim_vocab.contradicts` returning False → the first two tests go red.
"""
from __future__ import annotations

from i18n import langs

from ._claim_scene import review, said


def test_a_yes_with_sin_verificar_in_the_same_sentence_is_no_lo_tengo_verificado(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    out = said("Sí, cumple las dos cosas, aunque sin verificar en la ficha. Te dejo el enlace en la hoja.",
               "¿Cumple las dos?", sheets=("washer_es",), errand=False)
    assert out.startswith(langs.spec("es").claim_not_verified) and "Sí, cumple" not in out
    assert "Te dejo el enlace en la hoja." in out


def test_a_yes_with_not_verified_about_a_named_row_names_what_is_not_verified(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    out = said("Yes, the 699 one is new, though that's not verified yet.", "is the 699 one new?",
               sheets=("phone_699_us",))
    assert not out.startswith("Yes") and "«iphone 17 256gb»" in out and "new" in out


def test_quoting_the_words_or_saying_only_not_verified_stands(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    honest = "La Evvo Terra de 329: la clase energética está sin verificar en la ficha."
    quoted = 'Sí, tranquilo: todo lleva el filtro de piscina en ficha, así que nada de "sin confirmar".'
    for reply in (honest, quoted):
        assert not [c for c in review(reply, "", sheets=("washer_es",))["cut"] if c["why"] == "yes_and_unverified"]
