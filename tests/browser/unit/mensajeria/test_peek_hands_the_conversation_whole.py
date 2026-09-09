"""V2-624 — `peek`: a conversation handed WHOLE to the brain, so the model can summarize or extract in the
turn («dame la información relevante del grupo del viaje», «la esencia de esos 20 correos») without opening
anything on screen and without writing a byte to memory. The thread store IS the segregated data; analysis is
a READ of it — the operator's own storage doctrine («no quiero indexar el pasado»).
"""
from __future__ import annotations

import time

import pytest

from widgets import store as wstore
from widgets.mensajeria import data, views


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    yield


def _seed(msgs=None, name="Grupo Viaje", is_group=True):
    now = time.time()
    db = data.load_db()
    msgs = msgs if msgs is not None else [
        {"id": "m1", "dir": "in", "who": "Ana", "body": "He mirado vuelos a Marrakech el 12", "ts": now - 7200,
         "read": False},
        {"id": "m2", "dir": "in", "who": "Luis", "body": "Yo puedo del 12 al 19", "ts": now - 7000, "read": False},
        {"id": "m3", "dir": "out", "who": "Tú", "body": "me apunto", "ts": now - 6000, "read": True},
    ]
    db["threads"] = {"whatsapp|999": {"name": name, "isGroup": is_group, "complete": False,
                                       "touched": now, "msgs": msgs}}
    wstore.save("mensajeria", db)
    return now


def test_peek_by_name_returns_the_messages_and_the_group_flag():
    _seed()
    r = data.answer_action("peek", {"name": "grupo viaje"})
    res = r["result"]
    assert res["isGroup"] is True and res["held"] == 3 and res["returned"] == 3
    assert [m["from"] for m in res["messages"]] == ["Ana", "Luis", "Tú"]
    assert "Marrakech" in res["messages"][0]["body"]
    assert res["messages"][2]["dir"] == "out", "his own replies are part of the conversation being analyzed"


def test_peek_falls_back_to_the_open_conversation():
    _seed()
    db = data.load_db()
    db["active_chat"] = {"platform": "whatsapp", "chatId": "999"}
    wstore.save("mensajeria", db)
    r = data.answer_action("peek", {})
    assert r["result"]["returned"] == 3


def test_peek_unknown_teaches_the_shape():
    _seed()
    r = data.answer_action("peek", {"name": "nadie con este nombre"})
    assert r["ok"] is False and "name" in r["error"]


def test_peek_empty_thread_names_the_doors_to_more():
    """A chat we can NAME (a pending item) whose conversation store holds nothing yet: the refusal must name
    the doors that fill it (load_more / fetch_now), not just say no."""
    db = data.load_db()
    db["items"] = [{"platform": "whatsapp", "chatId": "777", "messageId": "w7", "from": "Nuevo Contacto",
                    "body": "hola", "urgencia": "media", "dirigido_a_mi": True}]
    wstore.save("mensajeria", db)
    r = data.answer_action("peek", {"platform": "whatsapp", "chatId": "777"})
    assert r["ok"] is False
    assert "load_more" in r["error"] and "fetch_now" in r["error"]


def test_the_budget_keeps_the_newest_messages():
    """40 long messages do not ride whole into one turn: the budget clamps, and what survives is the NEWEST
    end — the question is almost always about what is being said now."""
    now = time.time()
    msgs = [{"id": f"m{i}", "dir": "in", "who": "Ana", "body": f"[{i}] " + ("x" * 600),
             "ts": now - (40 - i) * 60, "read": True} for i in range(40)]
    _seed(msgs=msgs, name="Larga", is_group=False)
    r = data.answer_action("peek", {"name": "larga"})
    res = r["result"]
    assert res["held"] == 40
    assert res["returned"] < 40, "the char budget must clamp"
    # Each body is individually capped AND the survivors are the newest ones, in order.
    assert all(len(m["body"]) <= views._PEEK_MAX_BODY for m in res["messages"])
    assert res["messages"][-1]["body"].startswith("[39]")
    first_kept = int(res["messages"][0]["body"][1:].split("]")[0])
    assert first_kept == 40 - res["returned"], "survivors must be the newest contiguous tail"
