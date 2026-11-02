"""A sure question that asks to be TOLD is answered by a report — the promise repair does not turn it into an act (node 2.407).

V2-834 T19, use case `find-a-future-release-and-remind-me` (sandbox, 2026-11-02): «¿Seguro que el aviso del 2 de
diciembre está realmente programado? Dime de qué serie dice el aviso y confírmame que queda guardado.» — request_type
`question` (0.70), wants_words `tell` (1.00). The model answered from the state («está guardado… no lo he vuelto a
tocar») with no tool; the promise repair read that report as an act owed and ran `agenda:add_reminder` — a duplicate
reminder, under words saying nothing was touched.

Mechanism pinned here: the repair's own gate (`split_by_errand.holds_the_repair`) holds when the verdict is a sure
question AND a sure tell; a polite order («¿podrías apuntarla?», wants_words `act`) is still repaired.
"""
from __future__ import annotations

import threading

import pytest

from nucleo.turn import split_by_errand as sbe


def _brief(**verdicts):
    ev = threading.Event()
    ev.set()
    return {"event": ev, "result": {k: {"choice": c[0], "confidence": c[1], "probs": {c[0]: c[1]}}
                                    for k, c in verdicts.items()}, "_call_id": "t", "turn_id": "t", "open_ids": []}


@pytest.mark.parametrize("said", [
    "¿Seguro que el aviso del 2 de diciembre está realmente programado? Confírmame que queda guardado.",
    "Are you sure the December 2 reminder is really set? Tell me it is saved.",
])
def test_a_sure_report_question_holds_the_repair(said):
    b = _brief(request_type=("question", 0.70), wants_words=("tell", 1.0))
    assert sbe.holds_the_repair("Sí, está guardado y suena el 2 de diciembre.", said, b)


@pytest.mark.parametrize("verdicts", [
    {"request_type": ("question", 0.70), "wants_words": ("act", 0.95)},     # a polite order: «¿podrías apuntarla?»
    {"request_type": ("order", 0.95), "wants_words": ("tell", 0.90)},
    {"request_type": ("question", 0.30), "wants_words": ("tell", 1.0)},      # not sure it is a question
])
def test_an_order_is_still_repaired(verdicts):
    assert not sbe.holds_the_repair("Te la apunto.", "¿podrías apuntarme la cita del dentista?", _brief(**verdicts))


def test_a_question_over_the_licence_holds_under_his_seventy():
    """T48 (measured, dentist-appointment-into-agenda 2026-11-02 11:19): «¿en qué quedamos: el aviso era a la una o a
    las doce? Confírmame la hora exacta» read `question` 0.68 / `tell` 1.00. With the hold raised to the operator's 70 %
    (T38) it no longer held, and the repair wrote the reminder again over a question. Holding needs no more than the
    licence; the 70 % is the bar to ACT."""
    said = "Perdona, ¿en qué quedamos: el aviso era a la una o a las doce? Confírmame la hora exacta del aviso."
    assert sbe.holds_the_repair("Pues a las doce.", said, _brief(request_type=("question", 0.68), wants_words=("tell", 1.0)))
    assert not sbe.holds_the_repair("Pues a las doce.", said, _brief(request_type=("question", 0.40), wants_words=("tell", 1.0)))
