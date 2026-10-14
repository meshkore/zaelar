"""Node 2.686 — an attribute a reply states about a named row, that no source carries, is said as «not verified».

search-buy-phone__us (2026-10-14): «wait is the 699 one new?» → «Yes, the 699 listing is new and unused… not
refurbished»; «Is the 699 still available?» → «Yes — … at 699 is still available». The row carried «Producto NUEVO…:
?» and «Disponible…: ?». He named it by its PRICE, so the row is found by price as well as by title word. The claim
sentence goes, the honest line takes its place, and every other sentence of the reply stays.

Disarm: `_carried` returning True → both phone tests go red.
"""
from __future__ import annotations

from i18n import langs

from ._claim_scene import (PHONE_AVAILABLE, PHONE_HEARD_AVAILABLE, PHONE_HEARD_NEW, PHONE_NEW, PHONE_STEP,
                           WASHER_HEARD, WASHER_YES, review, said)


def test_new_and_unused_over_a_row_that_does_not_say_it_is_not_verified(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    r = review(PHONE_NEW, PHONE_HEARD_NEW, sheets=("phone_699_us",))
    out = " ".join(r["parts"])
    assert "Yes, the 699 listing is new" not in out and "open-box unit" not in out
    assert "verified for «iphone 17 256gb»: new, unused, not refurbished." in out
    assert "there are already candidates on the results sheet" in out          # the rest of the reply stays
    assert [c["why"] for c in r["cut"]] == ["attribute"]


def test_still_available_over_a_row_that_does_not_say_it_is_not_verified(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "en")
    out = said(PHONE_AVAILABLE, PHONE_HEARD_AVAILABLE, sheets=("phone_699_us",), evidence=(PHONE_STEP,))
    assert "is still available" not in out and "available" in out
    assert out.startswith(langs.spec("en").claim_unverified.split("{")[0])
    assert "Broad price sweep done (Phone House 929" in out                      # the worker's step is a source


def test_the_energy_class_the_title_does_not_carry_is_not_verified_in_spanish(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    out = said(WASHER_YES, WASHER_HEARD, sheets=("washer_es",))
    assert "Sí, la Evvo Terra" not in out
    assert "no tengo verificado: clase A. Sí consta: 8 kilos." in out          # the title says «8 Kg», not the class
    assert "la Balay y la SVAN quedan fuera" in out


def test_his_question_is_no_source_for_the_attribute(monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    r = review(WASHER_YES, WASHER_HEARD, sheets=("washer_es",), window=[{"role": "user", "content": WASHER_HEARD}])
    assert any(c["why"] == "attribute" for c in r["cut"])                         # «¿es de 8 kilos y clase A?» asks
