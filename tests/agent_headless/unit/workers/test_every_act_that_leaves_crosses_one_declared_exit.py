"""Every act of a worker that leaves the machine crosses ONE declared exit door (V2-857 phase 5).

The bridge used to choose the door by the act's name (`exit_gate.gate if action == "widget_data" else exit_gate.mesh`,
in two places), so a new leaving act — a booking by API, an invitation from a worker — had no door and no slot. Now the
acts that leave are DECLARED once (`exit_gate.EXITS`: the door each crosses and how its event type is read), the bridge
asks `exit_gate.leave(rec, action, payload)` and nothing by name, and every exit records one `task` event with the
event type (`messaging.send_new@whatsapp`, `errand.mesh_serve@mesh`), the person it reaches (the subject of phase 2),
the channel and its verdict. An act not declared there does not leave: `leave` is None and no door runs.
"""
from __future__ import annotations

import inspect
import time
from types import SimpleNamespace

import pytest

from nucleo.workers import exit_gate

TURNS = {"es": "escríbele a Raquel por WhatsApp que llego tarde", "en": "text Raquel on WhatsApp that I am running late"}


@pytest.fixture
def world(tmp_path, monkeypatch):
    from nucleo import his_words
    from nucleo.workers.prompts import playbook
    from widgets import contract, directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    cd.apply_action("add_contact", {"name": "Raquel Jofre", "phone": "680 762 886"})
    assert directory.note_inbound("whatsapp", {"chatId": "34680762886@s.whatsapp.net", "senderId": "34680762886@s.whatsapp.net", "from": "Raquel"})
    raquel = next(c["id"] for c in cd.load_db()["contacts"] if c["name"].startswith("Raquel"))
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    his_words.reset()
    seen: list[dict] = []
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        (seen.append({"kind": kind, "label": label, **(extra or {})}) if str(label).startswith("🚪") else None)
                        or real(kind, label, text=text, role=role, extra=extra))
    rec = SimpleNamespace(task_id="x5", playbook_chosen="errand", uid="", started=time.time(), depth=0, trace_id="",
                          surface="", sheet="", mandate={}, reading=None)
    yield SimpleNamespace(rec=rec, raquel=raquel, seen=seen)
    his_words.reset()


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_workers_send_crosses_the_door_as_its_event_type_with_its_person(world, lang):
    from nucleo import his_words
    his_words.note(TURNS[lang])
    ex = exit_gate.leave(world.rec, "widget_data", {"widget_id": "mensajeria", "action": "send_to",
                                                    "payload": {"contact": "Raquel", "text": "llego tarde", "platform": "whatsapp"}})
    assert ex is not None and ex.refused == ""
    assert ex.event == "messaging.send_new@whatsapp" and ex.subject == world.raquel
    (ev,) = world.seen
    assert ev["kind"] == "task" and ev["event"] == "messaging.send_new@whatsapp" and ev["subject"] == world.raquel
    assert ev["channel"] == "whatsapp" and ev["who"] == ["Raquel"] and ev["verdict"] == ex.verdict and ev["id"] == "x5"


def test_an_errand_to_a_network_agent_is_its_own_declared_event(world, monkeypatch):
    from connectors.meshkore import security
    monkeypatch.setattr(security, "enabled", lambda: True)
    monkeypatch.setattr(security, "scan_outbound", lambda t: (t, None))
    ex = exit_gate.leave(world.rec, "mesh_serve", {"prompt": "find a plumber in Girona", "agent": "ag-1"})
    assert ex is not None and ex.event == "errand.mesh_serve@mesh" and ex.subject == ""
    assert world.seen[-1]["event"] == "errand.mesh_serve@mesh" and world.seen[-1]["channel"] == "mesh"


def test_an_act_that_does_not_leave_crosses_no_door(world):
    assert exit_gate.leave(world.rec, "read_widget", {"widget_id": "agenda"}) is None
    assert exit_gate.leave(world.rec, "show_widget", {"widget_id": "agenda"}) is None
    assert world.seen == []


def test_the_bridge_and_the_answer_ask_the_one_door_and_nothing_by_name():
    from nucleo.cli import worker_api, worker_api_answer
    for mod in (worker_api, worker_api_answer):
        src = inspect.getsource(mod)
        assert "exit_gate.leave(" in src
        assert "exit_gate.gate if" not in src and '("widget_data", "mesh_serve")' not in src
    assert {s.action for s in exit_gate.EXITS} == {"widget_data", "mesh_serve"}


def test_disarmed_with_nothing_declared_a_send_leaves_through_no_door(world, monkeypatch):
    monkeypatch.setattr(exit_gate, "EXITS", ())
    assert exit_gate.leave(world.rec, "widget_data", {"widget_id": "mensajeria", "action": "send_to",
                                                      "payload": {"contact": "Raquel", "text": "x", "platform": "whatsapp"}}) is None, \
        "the disarm did not take"
    assert world.seen == [], "with no declaration the send crossed no door and left no record"
