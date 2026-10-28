"""A turn that ends by asking HIM, or that reports on a worker already running on what he named, owes no «I haven't
done it» (node 2.923).

Live replay, 2026-10-28 (build 405c4627b): «check the chat» → «…20 chats with something pending… Which one do you
mean — SOMOS Invernadero, Luis, or the ones about the Dexter question?» + «I haven't done it — I couldn't carry it out
from here.»; «continue with my Dexter request» while the Dexter worker ran → «…the background check is still on the
Dexter question and hasn't reported back yet…» + the same line. The brief read both as orders and nothing ran in the
turn, so `owed` said the line was due; the two facts that say otherwise were not read: the reply's verdict is «asked»
when it ends with a question to him, and «started» when a live errand already carries his words.

Disarm: with `asks_him` answering False, the first test goes red; with `an_errand_is_live_for` answering False, the third.
"""
from __future__ import annotations

import pytest

from nucleo.turn import promise_kept as pk
from nucleo.turn import reply as R

ORDER = "a brief that reads an order"


@pytest.fixture(autouse=True)
def _order(monkeypatch):
    monkeypatch.setattr(R, "owes_an_act", lambda brief: "order" if brief == ORDER else "")
    monkeypatch.setattr(pk, "_state_holds", lambda open_ids=None: False)
    monkeypatch.setattr(pk, "words_were_the_act", lambda brief: False)
    monkeypatch.setattr(pk, "_not_kept_line", lambda: "I haven't done it.")


@pytest.mark.parametrize("reply", [
    "There are 20 chats with something pending. Which one do you mean — Luis, or the ones about Dexter?",
    "Hay 20 chats con algo pendiente. ¿Cuál quieres, el de Luis o el de la cena?",
    "Which one exactly? I have «comedor del niño» 2026-10-28 14:30 and 2026-10-29 14:30.",
])
def test_a_reply_that_ends_asking_him_owes_nothing(reply, monkeypatch):
    monkeypatch.setattr(pk, "an_errand_is_live_for", lambda t: False)
    assert pk.honest_line(reply, {}, acted=False, brief=ORDER, op_text="check the chat") == ""


def test_a_claim_that_asks_nothing_is_still_said_undone(monkeypatch):
    monkeypatch.setattr(pk, "an_errand_is_live_for", lambda t: False)
    assert pk.honest_line("Done, I've cleared your chats.", {}, acted=False, brief=ORDER, op_text="check the chat") \
        == "I haven't done it."


def test_a_status_report_on_a_live_errand_that_carries_his_words_owes_nothing(monkeypatch):
    from nucleo.dispatch import registry
    monkeypatch.setattr(registry, "active_sessions", lambda now=None: [
        {"id": "9f15b8-1", "goal": "Verify, for a user in Spain, where Dexter: Resurrection S2 streams", "title": ""}])
    assert pk.an_errand_is_live_for("contonue with my desxter request") is False   # a typo names nothing: honest
    assert pk.an_errand_is_live_for("continue with my dexter request") is True
    reply = "The background check is still on the Dexter question and hasn't reported back yet."
    assert pk.honest_line(reply, {}, acted=False, brief=ORDER, op_text="continue with my dexter request") == ""
    assert pk.honest_line(reply, {}, acted=False, brief=ORDER, op_text="book me a dentist") == "I haven't done it."
