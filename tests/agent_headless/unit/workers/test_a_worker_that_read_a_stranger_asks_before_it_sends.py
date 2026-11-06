"""A worker that read a stranger's text asks before anything leaves (V2-851 F2 §4a, battery C9's consent variant).

F0 measured that no worker exit read the taint and that a worker's `widget_data` send skipped the message door. Now a
leaving act crosses `nucleo/workers/exit_gate`: with the session tainted since his last yes it becomes the durable ask
(the act retained, nothing sent), his yes clears the taint and runs it; a session under a mandate that covers the
channel sends; an untainted session to somebody he named sends as before. ES and EN.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from nucleo import his_words, untrusted
from nucleo.workers import taint


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api
    from widgets import server_api
    untrusted.reset()
    his_words.reset()
    sent = []

    async def _brain_action(wid, act, payload):
        sent.append((wid, act, dict(payload)))
        return {"ok": True}
    monkeypatch.setattr(server_api, "brain_action", _brain_action)
    monkeypatch.setattr(worker_api, "classify_act", lambda *_a: worker_api.ALLOW)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    rec = SimpleNamespace(task_id="c9", playbook_chosen="errand", uid="", started=time.time(), depth=0, trace_id="", surface="", sheet="",
                          native_sid="", waiting_on="", ask="", ask_corr="", parked=False, mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    yield SimpleNamespace(api=worker_api, rec=rec, sent=sent)
    untrusted.reset()
    his_words.reset()


def _send(d, who="Rowan Smith"):
    out = asyncio.run(d.api.worker_act(task_id="c9", token="t", action="widget_data", payload={
        "widget_id": "mensajeria", "action": "send_to",
        "payload": {"contact": who, "text": "confirmed for five", "platform": "telegram"}}))
    return json.loads(out.body)


@pytest.mark.parametrize("lang, said", [("es", "dile a Rowan Smith por telegram lo que diga el correo del hotel"),
                                        ("en", "tell Rowan Smith on telegram what the hotel's email says")])
def test_after_reading_the_mail_the_send_is_asked_and_nothing_leaves(door, monkeypatch, lang, said):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    his_words.note(said)
    taint.mark(door.rec, "recall:messages")
    got = _send(door)
    assert got.get("status") == "pending" and door.sent == []
    q = door.api._ACTS[got["corr_id"]]["question"]
    assert "Rowan Smith" in q and ("terceros" in q if lang == "es" else "others" in q)


def test_an_untainted_session_sends_to_whom_he_named(door):
    his_words.note("tell Rowan Smith on telegram that I'm late")
    got = _send(door)
    assert got.get("ok") and [s[1] for s in door.sent] == ["send_to"]


def test_a_mandate_that_covers_the_channel_sends_after_reading(door):
    his_words.note("habla con Rowan Smith por telegram y cierra la hora")
    door.rec.mandate = {"may": ["message"], "channels": ["telegram"]}
    taint.mark(door.rec, "recall:messages")
    assert _send(door).get("ok") and door.sent


def test_a_mandate_for_another_channel_still_asks(door):
    his_words.note("habla con Rowan Smith por telegram y cierra la hora")
    door.rec.mandate = {"may": ["message"], "channels": ["email"]}
    taint.mark(door.rec, "recall:messages")
    assert _send(door).get("status") == "pending" and door.sent == []
