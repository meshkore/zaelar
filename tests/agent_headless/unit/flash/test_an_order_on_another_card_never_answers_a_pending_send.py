"""An order on another card never answers a pending send (demo pass 134, 2026-10-15, E3→C3).

The forward to Quinn was waiting on «Shall I send it?». The next turn, «ok book it, call it catch up with rowan»,
matched `ok`, the early door resolved the forward, the mail went (with no note) and the meeting was never booked.
The verdict had SURELY named `agenda:add_meeting`. Now: a reply longer than a plain yes whose verdict surely names
an action on ANOTHER card does not answer the pending question; and for a pending act that leaves, a longer reply
with no reader to judge it never sends on a word. A plain «yes» still answers, and other pending acts keep the words.
"""
import pytest

from widgets import confirm as C


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    C._PENDING.clear()
    monkeypatch.setattr(C, "_judge", lambda q, t, timeout=4.0: None)      # no reader, as in the suite
    yield
    C._PENDING.clear()


def _verdict(monkeypatch, card: str, action: str, sure: bool = True):
    from nucleo.flash import direct_action as DA
    monkeypatch.setattr(DA, "from_brief", lambda b: (card, action))
    monkeypatch.setattr(DA, "_action_sure", lambda b, floor=0.8: sure)


def _pending_send():
    C.request("data", "mensajeria", "Shall I send it?", op={"action": "forward", "payload": {}}, notify_ui=False)


def test_an_order_on_the_agenda_is_not_a_yes_to_the_mail(monkeypatch):
    _pending_send()
    _verdict(monkeypatch, "agenda", "add_meeting")
    assert C.answers_pending("ok book it, call it catch up with rowan", brief=object()) is None


def test_with_no_reader_a_longer_sentence_never_sends(monkeypatch):
    _pending_send()
    _verdict(monkeypatch, "", "")
    assert C.answers_pending("ok and also tell me the weather", brief=object()) is None


def test_a_plain_yes_still_sends(monkeypatch):
    _pending_send()
    _verdict(monkeypatch, "agenda", "add_meeting")
    assert C.answers_pending("yes", brief=object()) == "yes"


def test_a_pending_delete_keeps_the_words(monkeypatch):
    C.request("delete", "agenda", "Delete the agenda?", notify_ui=False)
    _verdict(monkeypatch, "", "")
    assert C.answers_pending("ok go ahead and do it now please", brief=object()) == "yes"
