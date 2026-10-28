"""A slice of the inbox proves no absence (demo pass 143, E1 on its second round, 2026-10-19).

«check my email, did inworld send me something?» → `mensajeria:show_view {platform: email}`, the PENDING lens; the
receipt had left it when the previous round forwarded it, and the op's rows were composed as THE RECORD — «nothing
from Inworld». A lens the card declares `subset` answers with the card's own `read_query` rows for his words, and
with none the pass is told it looked at a slice. A lens that is the whole answer (`agenda:show_day`) is unchanged.
"""
import inspect

import pytest

from nucleo.flash import widget_read

RECORD = "Del ARCHIVO permanente… · 2026-09-27 11:58 · email · Inworld AI <inworld> · Your receipt from Inworld AI #2281"
PENDING = {"platform": "email", "count": 1, "chats": [{"n": 2, "name": "AliExpress", "platform": "email"}]}


@pytest.fixture
def asked(monkeypatch):
    seen = []

    def fake(wid, q):
        seen.append((wid, q))
        return RECORD if "inworld" in q.lower() else ""
    monkeypatch.setattr(widget_read, "lookup", fake)
    return seen


def _sys(said, ops, wid="mensajeria", data=PENDING):
    return widget_read.op_answer_system("", said, wid, data, ops)


def test_a_subset_lens_answers_with_the_record_for_his_words(asked):
    out = _sys("check my email, did inworld send me something?", [("mensajeria", "show_view")])
    assert RECORD in out and "EL REGISTRO" in out and asked == [("mensajeria", "check my email, did inworld send me something?")]


def test_with_no_record_rows_the_slice_is_never_read_as_everything(asked):
    out = _sys("¿me ha escrito el colegio?", [("mensajeria", "show_view")])
    assert "RESUMEN" in out and "EL REGISTRO" not in out


def test_a_lens_that_is_the_whole_answer_is_unchanged(asked):
    out = _sys("what's on my plate tomorrow", [("agenda", "show_day")], wid="agenda", data={"day": "2026-10-20"})
    assert "EL REGISTRO" in out and asked == []


def test_the_turn_composes_through_the_one_door():
    from nucleo.flash import post_stream_acts
    src = inspect.getsource(post_stream_acts)
    assert "op_answer_system(" in src and "answered=True" not in src
