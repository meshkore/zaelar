"""A yes to an act that leaves the machine is HIS, never the model's (demo pass 133, 2026-10-15, E3→E4).

The forward of the Inworld receipt to Andrew asked «Shall I send it?». The next turn was «oh and leave that inworld one
as unread», and the model answered the question itself — `confirm_widget_delete(confirmed=true)` — so the mail went
out on a sentence that never said yes. For a pending act that leaves (`external.send`), the model's yes resolves only
when his words give it (`widgets.confirm.backs_a_yes`); otherwise nothing is resolved and the question is asked again.
A pending delete (it has a trash and a restore) keeps the model's reading.
"""
import pytest

from nucleo.flash import tool_executor_calls as TEC
from widgets import confirm as C


@pytest.fixture(autouse=True)
def clean():
    C._PENDING.clear()
    yield
    C._PENDING.clear()


def _answer(said: str):
    resolved, clarify = [], {"msg": ""}
    out = TEC._t_confirm({"confirmed": True}, said, lambda ok: resolved.append(ok) or True, clarify,
                         lambda *a, **k: None)
    return out, resolved, clarify["msg"]


def _pending_send():
    C.request("data", "mensajeria", "Shall I send it?", op={"action": "forward", "payload": {"contact": "Andrew"}},
              notify_ui=False)


def test_a_sentence_about_something_else_does_not_send(monkeypatch):
    _pending_send()
    assert _answer("oh and leave that inworld one as unread") == (False, [], "Shall I send it?")
    assert C.pending(), "the question is still waiting for him"


def test_his_yes_sends():
    _pending_send()
    assert _answer("yes") == (True, [True], "")


def test_a_pending_delete_keeps_the_models_reading():
    C.request("delete", "agenda", "Delete the agenda?", notify_ui=False)
    assert _answer("go on then, bin it")[1] == [True]
