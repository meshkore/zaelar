"""A reply that says «there is nothing» does not survive the delivery of rows (V2-782) — search-buy-used-car ES/EN.

Measured: «No hay nada que mostrar: no aparece ningún modelo ni precio en la búsqueda. Bueno, de hecho ya hay candidatos
en la hoja de resultados: «Fiat Tipo — € 10.490»…». The delivery is the fact; the denial goes, and so does the
«actually» lead that only made sense after it.
"""
from __future__ import annotations

from nucleo.flash import nothing_claims

DELIVERY_ES = "Bueno, de hecho ya hay candidatos en la hoja de resultados: «Fiat Tipo — € 10.490». Dime si alguno te encaja."
DELIVERY_EN = "Actually, there are already candidates on the results sheet: «2018 Ford Fusion — $13,397»."


def test_the_measured_spanish_reply_loses_its_denial():
    out = nothing_claims.reconcile("No hay nada que mostrar: no aparece ningún modelo ni precio en la búsqueda.", DELIVERY_ES)
    assert out.startswith("Ya hay candidatos en la hoja de resultados: «Fiat Tipo")
    assert "No hay nada" not in out and "de hecho" not in out


def test_the_english_shape_keeps_what_was_true():
    out = nothing_claims.reconcile("There's nothing solid yet. The search is on step 2 of 5.", DELIVERY_EN)
    assert out == "The search is on step 2 of 5. " + DELIVERY_EN


def test_a_reply_without_a_denial_is_untouched():
    assert nothing_claims.reconcile("Sigo con ello.", DELIVERY_ES) == "Sigo con ello. " + DELIVERY_ES


def test_the_delivery_backstop_reconciles_through_it(monkeypatch):
    from nucleo.flash import delivery, live_blocks
    monkeypatch.setenv("ZAELAR_LANGUAGE", "es")
    delivery.forget_announced()
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: ("coche diésel", ["Fiat Tipo — € 10.490"]))
    out = delivery.apply_to_reply("No hay nada que mostrar: no aparece ningún modelo ni precio en la búsqueda.",
                                  [{"role": "user", "content": "¿qué te sale?"}], heard_now="¿qué te sale?")
    assert "«Fiat Tipo — € 10.490»" in out and "No hay nada" not in out
