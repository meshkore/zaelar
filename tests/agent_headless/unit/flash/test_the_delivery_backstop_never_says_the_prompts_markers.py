"""The delivery backstop says rows as SPEECH — never the prompt's internal markers (V2-781, hotel-under-15-days__us).

The sheet's rows are formatted for the PROMPT (`errand_sheet._linea`): «Name — SIN PRECIO» tells the model a row has
no price, «— PÁGINA WEB por mirar…» that it is only a lead. The backstop glued those lines verbatim to the reply, so
an English session heard «Best Western PLUS Island Palms… — SIN PRECIO» three times.
"""
from nucleo.flash import delivery


def test_the_no_price_marker_is_not_said(monkeypatch):
    monkeypatch.setattr(delivery, "_speaks_en", lambda: True)
    out = delivery.sheet_delivery_backstop("Still on it.", ["Humphreys Half Moon Inn — SIN PRECIO",
                                                            "The Dana on Mission Bay — 189 €"], errand="hotel san diego")
    assert "SIN PRECIO" not in out and "Humphreys Half Moon Inn" in out and "189 €" in out


def test_a_bare_lead_is_not_announced_as_a_candidate(monkeypatch):
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    out = delivery.sheet_delivery_backstop("Sigo con ello.", ["Hoteles baratos 2026 — PÁGINA WEB por mirar, aún no es "
                                                              "un candidato"], errand="hotel")
    assert out == ""
