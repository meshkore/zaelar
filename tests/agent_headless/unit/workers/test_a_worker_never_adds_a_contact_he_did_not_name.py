"""A worker never adds to his directory a business he did not name — by the action or by the generic door.

`best-plumber-same-day__es` (2026-10-14): `contactos add_contact {name: «Fontanero Urgencia Madrid», phone:
683139819}` and `{name: «Fontaurgencias 24h», …}` ran from the worker with nobody asking: a stranger in his
contacts is the step that makes the next `send_to` resolve. `add_contact` declares `on_his_behalf: "name"`
in its manifest, and `rows.put` over `contacts` runs `add_contact` (`collections.contacts.via.put`), so the
generic door is the same act.
"""
import time

import pytest

from nucleo import his_words, on_his_behalf


class _Rec:
    task_id = "1"

    def __init__(self):
        self.started = time.time()


@pytest.fixture(autouse=True)
def _clean():
    his_words.reset()
    his_words.note("Tengo una fuga en el baño y necesito un fontanero hoy sí o sí… uno que esté bien valorado")
    his_words.note("Madrid centro")
    yield
    his_words.reset()


def _q(action, payload):
    return on_his_behalf.worker_question(_Rec(), "widget_data",
                                         {"widget_id": "contactos", "action": action, "payload": payload})


def test_the_manifest_declares_who_the_contact_is():
    assert on_his_behalf.acts_for_him("contactos", "add_contact")
    assert on_his_behalf.who_of("contactos", "add_contact", {"name": "Fontaurgencias 24h", "phone": "610"}) \
        == ["Fontaurgencias 24h"]


def test_the_two_plumbers_of_the_session_ask():
    assert "Fontanero Urgencia Madrid" in _q("add_contact", {"name": "Fontanero Urgencia Madrid",
                                                              "phone": "683139819"})
    assert _q("add_contact", {"name": "Fontaurgencias 24h", "phone": "610967897"}) != ""


def test_the_generic_door_is_the_same_act():
    assert _q("rows.put", {"collection": "contacts", "row": {"name": "Fontaurgencias 24h"}}) != ""


def test_one_he_named_is_saved_without_a_question():
    """«guárdame al fontanero García» — the number the worker found is data, the WHO is his."""
    his_words.note("busca el teléfono de Fontanería García y guárdamelo en contactos")
    assert _q("add_contact", {"name": "Fontanería García", "phone": "915550000"}) == ""


def test_editing_a_contact_he_has_is_not_this_gate():
    assert _q("update_contact", {"contactId": "c1", "notes": "viene a las 5"}) == ""
