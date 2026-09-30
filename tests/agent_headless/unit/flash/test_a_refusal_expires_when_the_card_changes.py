#
# test_a_refusal_expires_when_the_card_changes.py — demo pass 31 (2026-09-28), E2 → E3 → E4.
#
# «open it» sent `mensajeria:open {name: Inworld}` 3 s before the mail's history fetch landed on the card, and
# the card refused it. One turn later the mail WAS there, the model asked for the same open, and the V2-773 guard
# («the same op cannot succeed where it just failed») ate it — twice. The forward to Quinn never went out and
# E4 said «Done». The guard's premise holds only while the card holds what it held.
#
import pytest

from nucleo.flash import data_ops
from widgets import store


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    data_ops._REFUSED["v"] = None
    yield
    data_ops._REFUSED["v"] = None


_OPEN = ("mensajeria", "open", {"name": "Inworld"})


def test_the_same_refused_call_on_an_unchanged_card_is_still_ignored():
    store.save("mensajeria", {"items": []})
    data_ops.remember_refusal(*_OPEN)
    assert data_ops.is_identical_retry_of_refused(*_OPEN)


def test_once_new_data_lands_on_the_card_the_retry_runs():
    store.save("mensajeria", {"items": []})
    data_ops.remember_refusal(*_OPEN)
    store.save("mensajeria", {"items": [{"from": "Inworld", "subject": "Your receipt"}]})
    assert not data_ops.is_identical_retry_of_refused(*_OPEN), \
        "the mail arrived after the refusal and the open was still thrown away"


def test_an_idempotent_poll_does_not_count_as_a_change():
    store.save("mensajeria", {"items": []})
    data_ops.remember_refusal(*_OPEN)
    store.save("mensajeria", {"items": []})
    assert data_ops.is_identical_retry_of_refused(*_OPEN)


def test_another_cards_change_does_not_lift_it():
    store.save("mensajeria", {"items": []})
    data_ops.remember_refusal(*_OPEN)
    store.save("agenda", {"meetings": [{"title": "x"}]})
    assert data_ops.is_identical_retry_of_refused(*_OPEN)
