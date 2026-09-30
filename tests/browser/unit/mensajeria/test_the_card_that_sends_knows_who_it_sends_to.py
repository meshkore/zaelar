"""A question put to the messaging card about a recipient is answered from the directory it sends through.

Demo pass 2026-09-28, C5: «send rowan a telegram with the new time» → the model asked the messaging card «is there a
contact called Rowan? does he have Telegram?», got only the inbox, answered «I can't find any contact named
Rowan», and a Brain Worker spent a minute sending what `send_to` would have sent at once.
"""
import pytest


@pytest.fixture
def stores(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as ct
    ct.apply_action("add_contact", {"name": "Rowan", "city": "San Mateo", "preferred": "telegram",
                                    "channels": [{"platform": "telegram", "handle": "@cryptonite_fund",
                                                  "chatId": "7477656357"}]})


def test_the_recipient_he_asks_about_is_in_the_answer(stores):
    from widgets.mensajeria import data as msg
    out = msg.read_query("Is there a contact called Rowan? Does he have Telegram?")
    assert "Rowan" in out and "@cryptonite_fund" in out and "telegram" in out.lower()


def test_a_question_about_nobody_known_adds_nothing(stores):
    from widgets.mensajeria import data as msg
    assert "Rowan" not in msg.read_query("any news from the plumber?")
