"""V2-778 F0-3 — a negation subtracts only the act it governs, and only inside its own clause.

`danger._drop_negated_acts` (2026-09-29) drops «do not buy anything yet» before the money verbs are read, so a
rewrite that says what will NOT happen is not parked as a charge. Its window had two holes, measured by the
self-audit of 2026-09-30:

  · up to three words could sit between the negation and the verb, so «don't FORGET TO pay the invoice» and
    «without further delay pay the invoice» — two orders to pay — lost their verb;
  · the drop ran to the end of the SENTENCE, so a comma did not stop it: «no compres el barato, compra este»
    lost «compra este», the order itself.

The repair keeps the technique (a subtraction, nothing added to the verb lists): the words in between may not
be a verb of their own that re-affirms the act (forget / fail / delay / olvidar / dejar de), and the drop ends
at the clause boundary — a comma, «y», «and», «but».
"""
from __future__ import annotations

import pytest

from nucleo import danger


@pytest.mark.parametrize("req", [
    "don't forget to pay the invoice",
    "without further delay pay the invoice",
    "no compres el barato, compra este",
    "no te olvides de pagar la factura",
    "do not buy the red one and buy the blue one",
])
def test_an_order_to_pay_beside_a_negation_still_parks(req):
    assert danger.is_dangerous(req) is True, req


@pytest.mark.parametrize("req", [
    "do not buy anything yet",
    "Do not search for or buy anything yet.",
    "no pagues la factura sin avisarme",
])
def test_a_negated_act_is_still_dropped(req):
    assert danger.is_dangerous(req) is False, req
