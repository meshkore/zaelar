"""«Dime a qué dentista vas y te la apunto…» is an OFFER, not a note (V2-781 pair 5, 2026-10-10).

The reply asked for a detail and promised the note on the condition of the answer: «Dime a qué dentista vas y te la
apunto con su aviso para el jueves 15 a las diez.» The dated-note backstop read «te la apunto» and filed an all-day
entry titled «con su aviso» on the 15th — which then showed up in «¿qué tengo el jueves?». A question mark already
stopped it; a reply that asks without one is still asking.
"""
from __future__ import annotations

from nucleo.flash import reminder_guards as R

REPLY = ("Ahora mismo no hay nada del dentista apuntado —la cita no llegó a guardarse porque me faltó el nombre de la "
         "clínica, así que no hay ficha que abrir. Dime a qué dentista vas y te la apunto con su aviso para el "
         "jueves 15 a las diez.")


def test_a_reply_that_asks_files_nothing():
    assert R.dated_note_backstop(REPLY, "Ábreme la ficha del dentista, que quiero verla") is None


def test_a_settled_promise_still_files():
    got = R.dated_note_backstop("Te apunto la renovación del seguro del coche para el jueves.",
                                "Apúntame que el jueves tengo que renovar el seguro del coche")
    assert got and "seguro" in str(got.get("title", "")).lower(), got
