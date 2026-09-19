"""fix03 · a spelling fragment cannot commission a worker — session 6d19df41.

Measured live: the operator spelled «Carwow» across STT fragments — «Scarborough.»
-> «It is» -> «car. W o w in the message list». The fragment «It is» reached the
model as a whole turn and the model commissioned a web-research Brain Worker for
it («Find and present information about "Scarborough" related to "car"…») — a
ghost the operator had to kill by voice («Stop this task immediately»).

`too_thin_to_commission` is structural, never topical: 1-3 words with no
directive (no verb of any guarded family, no question) is a fragment of a longer
utterance, not an errand. Anything it cannot judge behaves as before.
"""
from __future__ import annotations

from nucleo.flash import router_guards as _g


def test_session_fragments_are_thin():
    assert _g.too_thin_to_commission("Scarborough.")
    assert _g.too_thin_to_commission("It is")
    assert _g.too_thin_to_commission("It is car.")
    assert _g.too_thin_to_commission("car.")
    assert _g.too_thin_to_commission("W o w")
    assert _g.too_thin_to_commission("r")


def test_full_spelling_turn_is_not_thin():
    assert not _g.too_thin_to_commission("It is car. W o w in the message list.")


def test_orders_survive_in_both_languages():
    assert not _g.too_thin_to_commission("Cancelalo")
    assert not _g.too_thin_to_commission("para")
    assert not _g.too_thin_to_commission("sigue")
    assert not _g.too_thin_to_commission("pon musica")
    assert not _g.too_thin_to_commission("abre la agenda")
    assert not _g.too_thin_to_commission("open my messages")
    assert not _g.too_thin_to_commission("busca hoteles")
    assert not _g.too_thin_to_commission("investiga esto")


def test_questions_and_real_work_survive():
    assert not _g.too_thin_to_commission("Do you copy?")
    assert not _g.too_thin_to_commission("Hello?")
    assert not _g.too_thin_to_commission("cancela mi suscripcion")
    assert not _g.too_thin_to_commission("compara hoteles a fondo")


def test_empty_is_fail_open():
    assert not _g.too_thin_to_commission("")
    assert not _g.too_thin_to_commission("   ")
