"""A worker sends to somebody HE named without a second question (V2-719 kept beside the new gate).

V2-719 (2026-09-17, «Invite Ivan via Gmail»): the operator had written «send me a calendar invite to:
ivan@charms.dev» and said «asegúrate de que termine sin intervención humana»; the worker's invite parked on
«¿Lo autorizas?» anyway. The gate that stops a worker writing to a plumber he never named must not bring that
question back: a recipient named in his own words — by address, by number, by name — is his order.
"""
import time

import pytest

from nucleo import his_words, on_his_behalf


class _Rec:
    task_id = "4"

    def __init__(self):
        self.started = time.time()


@pytest.fixture(autouse=True)
def _clean():
    his_words.reset()
    yield
    his_words.reset()


def _q(widget, action, payload):
    return on_his_behalf.worker_question(_Rec(), "widget_data",
                                         {"widget_id": widget, "action": action, "payload": payload})


def test_an_address_he_wrote_is_his_order():
    his_words.note("send me a calendar invite to: ivan@charms.dev")
    assert _q("agenda", "invite", {"who": "ivan@charms.dev", "meeting": "Ivan"}) == ""


def test_a_number_he_said_is_his_order_even_with_a_prefix_he_did_not_say():
    his_words.note("mándale un whatsapp al 600 11 22 33 diciendo que llego tarde")
    assert _q("mensajeria", "send_to", {"to": "+34600112233", "text": "llego tarde"}) == ""


def test_a_name_he_said_is_his_order():
    his_words.note("dile a Rowan Smith por telegram que mañana no puedo")
    assert _q("mensajeria", "send_to", {"contact": "Rowan Smith", "text": "mañana no puedo"}) == ""


def test_one_name_he_said_does_not_carry_another():
    his_words.note("invita a ivan@charms.dev a la reunión")
    assert _q("agenda", "invite", {"who": "ivan@charms.dev, otro@ajeno.com", "meeting": "Ivan"}) != ""


def test_a_name_that_only_shares_his_words_is_not_his():
    """«Fontanero Urgencia Madrid» shares two words with «necesito un fontanero… Madrid centro»: the worker FOUND
    that business, he never named it — a phrase, not loose words, is what names somebody."""
    his_words.note("necesito un fontanero hoy sí o sí")
    his_words.note("Madrid centro")
    assert _q("mensajeria", "send_to", {"contact": "Fontanero Madrid", "text": "hola"}) != ""


def test_an_act_that_writes_to_nobody_is_not_this_gate():
    assert _q("agenda", "add_meeting", {"title": "dentista"}) == ""
    assert _q("mensajeria", "draft", {"n": 1, "text": "hola"}) == ""
