"""A money word that a PREPOSITION governs is the TOPIC, never the order (three-tasks-at-once, 2026-10-10).

Measured in the use-case round `three-tasks-at-once` (sandbox 20261010-145227-es). The operator asked «hazme un
informe sobre coches eléctricos para ciudad»; the fast brain composed the errand as «Elaborar un informe completo
… precio, tamaño/manejabilidad, COSTE DE RECARGA y mantenimiento …», and the gate parked it out loud as «Esto mueve
dinero (…) y no hago ningún cargo sin tu OK». A report about running costs was asked to authorise a charge.

The cause is one word: «recarga» sits in `_SPEND_VERB_RE` as the imperative («recarga el móvil»), and here it is
the NOUN — «coste DE recarga». The module already knew this shape for one word: «compra» after «de» is the
shopping, never the imperative (V2-748). The class is the preposition, not the word: a money form governed by
«de / del / por / para / en / of / per / for» names what something is ABOUT. The imperative it shares a spelling
with keeps stopping, and so does a real payment whose object happens to carry the noun.
"""
from __future__ import annotations

import pytest

from nucleo import danger

# The two rewrites of the measured round, verbatim.
REPORT_ES = ("Elaborar un informe completo sobre coches eléctricos para uso en ciudad: modelos disponibles, autonomía "
             "real en ciudad, precio, tamaño/manejabilidad, coste de recarga y mantenimiento, ventajas e "
             "inconvenientes frente a un urbano de combustión, y una recomendación razonada por perfiles de uso. "
             "Formato de informe escrito.")


@pytest.mark.parametrize("request_text", [
    REPORT_ES,
    "Compara el coste por recarga de tres patinetes eléctricos",
    "Write a report on the cost per charge of the main city EVs",
    "Hazme un resumen de los puntos de recarga de Madrid y su precio",
    "Prepara una guía de compra de portátiles para estudiantes",
])
def test_a_money_noun_after_a_preposition_is_not_a_charge(request_text):
    assert not danger.is_dangerous(request_text), request_text


@pytest.mark.parametrize("request_text", [
    "Recarga el móvil con 20 euros",
    "recarga la tarjeta del transporte",
    "transfiere 500 euros a la cuenta de Quinn",
    "Compra el pan",
    "paga por la compra del pedido",
    "confirma la compra",
    "finalizar compra",
    "charge my card for the order",
    "Haz un informe del coste de recarga y recarga el móvil con 10 euros",
])
def test_the_imperative_that_shares_the_spelling_keeps_stopping(request_text):
    assert danger.is_dangerous(request_text), request_text
