"""After the first delivery, the sheet's rows only ride a WAIT — a reply that answers him keeps the turn.

rental-car-automatic-airport (2026-10-11, ES and EN, one errand live): «Bueno, de hecho ya hay candidatos en la hoja
de resultados… Dime si alguno te encaja o sigo afinando» glued to four replies in a row, three of them answers to
«¿el Polo es automático y en el aeropuerto?». Twelve rows on the sheet, three new ones per tail, so every turn found
something «fresh». `nucleo/flash/delivery_repeat.py` holds the tail once the errand's rows were delivered, unless the
reply is a pure wait — the case the backstop exists for.
"""
from nucleo.flash import delivery, live_blocks

ERRAND = "Buscar alquiler de coche AUTOMÁTICO en el aeropuerto de Málaga"
ROWS = [f"Oferta {name} de EconomyBookings — {price} €" for name, price in (
    ("Fiat Panda", 90), ("Volkswagen Polo", 93), ("Opel Astra", 120), ("Volkswagen Taigo", 126),
    ("Seat Ibiza", 98), ("Toyota Yaris", 105), ("Renault Clio", 103), ("Kia Picanto", 94), ("Peugeot 208", 131))]


def _wire(monkeypatch):
    monkeypatch.setattr(live_blocks, "any_live_task_rows", lambda n=3: (ERRAND, list(ROWS)))
    monkeypatch.setattr(live_blocks, "any_stalled_task", lambda: ("", 0, ""))
    monkeypatch.setattr(delivery, "_speaks_en", lambda: False)
    delivery.forget_announced()


def test_the_round_as_measured_gets_ONE_tail_and_then_its_answers(monkeypatch):
    _wire(monkeypatch)
    first = delivery.apply_to_reply("Todavía no, sigue trabajando: va aún en ese primer paso.", [])
    assert "ya hay candidatos" in first
    answers = [
        ("No, del de 90 € no tengo guardado ni que sea automático ni que sea en el aeropuerto.",
         "¿seguro que es automático y en el aeropuerto?"),
        ("Voy a pedirle a la búsqueda que confirme eso del Polo y que descarte lo que no lo cumpla.",
         "El Polo me vale de tamaño, ¿puedes confirmarme que es automático?"),
        ("No, no te lo puedo asegurar de ninguno: lo que ha salido son precios sin desglose de cambio.",
         "¿Del Taigo o de cualquiera de esos me puedes asegurar eso?"),
    ]
    for reply, heard in answers:
        out = delivery.apply_to_reply(reply, [], heard_now=heard)
        assert out == reply, f"an answer got the tail again: {out!r}"


def test_a_later_WAIT_still_gets_the_new_rows(monkeypatch):
    _wire(monkeypatch)
    delivery.apply_to_reply("Todavía no, sigue trabajando.", [])
    later = delivery.apply_to_reply("Sigue en marcha, te aviso en cuanto tenga más.", [], heard_now="¿alguna novedad?")
    assert "ya hay candidatos" in later, "a wait with unannounced rows is exactly what the backstop is for"


def test_the_first_delivery_is_unchanged_whatever_the_reply(monkeypatch):
    _wire(monkeypatch)
    out = delivery.apply_to_reply("Noted, San Francisco.", [], heard_now="San Francisco")
    assert "ya hay candidatos" in out
