"""ONE reading of «did he name this recipient» for both brains (V2-851 F2, §15c).

Two implementations decided it: the worker's door read `on_his_behalf.named` (a literal phrase only) and Flash's send
gate read `acts.message.is_his` (named, or one of his words his directory gives to that person alone). The same
order then ran by voice and asked from a worker. Now the worker door calls `is_his` too, with `found=True` — the
recipient came from the worker's search, so a shared word over a name his directory does not hold is not naming it.
"""
from __future__ import annotations

import time

import pytest

from nucleo import his_words, on_his_behalf
from nucleo.acts import message


class _Rec:
    task_id = "w1"

    def __init__(self):
        self.started = time.time()


@pytest.fixture
def directory(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as cd
    cd.apply_action("add_contact", {"name": "Quinn Harper", "kind": "person", "email": "quinn@example.com",
                                    "channels": [{"platform": "email", "handle": "quinn@example.com"}],
                                    "preferred": "email"})
    his_words.reset()
    yield cd
    his_words.reset()


def _q(widget, action, payload):
    return on_his_behalf.worker_question(_Rec(), "widget_data",
                                         {"widget_id": widget, "action": action, "payload": payload})


@pytest.mark.parametrize("said, who", [
    ("escribe a quinn que llego tarde", "Quinn Harper"),
    ("tell quinn the meeting moved to five", "quinn@example.com"),
])
def test_a_directory_unique_word_names_him_for_the_worker_as_for_the_voice(directory, said, who):
    his_words.note(said)
    assert message.is_his(who, [said])                              # Flash's reading
    assert _q("mensajeria", "send_to", {"contact": who, "text": "hola"}) == ""      # the worker's, the same


def test_a_name_the_worker_found_is_not_his_by_a_shared_word(directory):
    said = "necesito un fontanero hoy, en Madrid centro"
    his_words.note(said)
    assert message.is_his("Fontanero Urgencia Madrid", [said])                       # composed from his words
    assert not message.is_his("Fontanero Urgencia Madrid", [said], found=True)       # found by a search
    assert _q("mensajeria", "send_to", {"contact": "Fontanero Urgencia Madrid", "text": "hola"}) != ""
