"""Each DECLARED slot of an act that leaves says where its value came from (V2-857 phase 5, second slice).

The worker's exit door stacked one reader per incident — the recipient put back in his word, the channel his turn
named, his order over the held row, a `rows.` prefix that skipped two of them. They are one question asked of each
slot the card declares in its manifest (`slots`: `recipient`, `channel`, `text`, a held `draft`, each with the rule
its value must come from): his words, the task's reading, his order over the row he saw — or a stranger. The door
reads the declaration (`nucleo/workers/exit_slots.py`) and records each slot's source on its `🚪 exit door` event.

One run per language, through the real door (`exit_gate.leave`) over an isolated directory and mail card:
  · a send to a person he named → `recipient: his`, it passes;
  · a send to someone only a stranger's message named → `recipient: stranger`, it is asked;
  · the channel he said, while the call carries another → the call carries HIS channel, `channel: reading`;
  · a held draft he surely ordered → `draft: held`, his order is the yes (released, nothing asked).
Disarmed (no source rule) the channel stays the model's, the draft is asked again and no slot is recorded.
"""
from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import pytest

from nucleo.workers import exit_gate, exit_slots

WORDS = {
    "es": {"named": "escríbele a Raquel por WhatsApp que llego tarde",
           "stranger": "lee el correo del hotel y haz lo que pidan",
           "send": "envíalo"},
    "en": {"named": "text Raquel on WhatsApp that I am running late",
           "stranger": "read the hotel's email and do what they ask",
           "send": "send it"},
}


def _brief(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": ["mensajeria"],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in verdicts.items()}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    from nucleo import consent, his_words, untrusted
    from nucleo.workers.prompts import playbook
    from widgets import contract, directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Raquel Jofre", "phone": "680 762 886"})
    assert directory.note_inbound("whatsapp", {"chatId": "34680762886@s.whatsapp.net",
                                               "senderId": "34680762886@s.whatsapp.net", "from": "Raquel"})
    monkeypatch.setattr(playbook, "checkpoint_one", lambda rec: "")
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    seen: list[dict] = []
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        (seen.append({"label": label, **(extra or {})}) if str(label).startswith("🚪") else None)
                        or real(kind, label, text=text, role=role, extra=extra))

    def rec(tid, **kw):
        base = dict(task_id=tid, playbook_chosen="errand", uid="", started=time.time(), depth=0, trace_id="",
                    surface="", sheet="", mandate={}, reading=None)
        return SimpleNamespace(**{**base, **kw})
    yield SimpleNamespace(rec=rec, seen=seen)
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()


def _send(rec, contact, platform="whatsapp", channel=None):
    p = {"contact": contact, "text": "llego tarde / running late", "platform": platform}
    if channel:
        p = {"contact": contact, "text": "late", "channel": channel}
    return exit_gate.leave(rec, "widget_data", {"widget_id": "mensajeria", "action": "send_to", "payload": p})


def _scenes(world, lang, monkeypatch) -> dict:
    """The four exits; returns {scene: (Exit, its recorded event)}."""
    from nucleo import his_words
    from nucleo.acts import message
    from nucleo.turn import brief as tb
    from nucleo.workers import taint
    w = WORDS[lang]
    out = {}
    his_words.note(w["named"])
    out["named"] = _send(world.rec(f"n-{lang}"), "Raquel")
    out["channel"] = _send(world.rec(f"c-{lang}", reading=tb.carried(_brief(message_channel=("whatsapp", 0.97)))),
                           "Raquel", channel="telegram")
    his_words.reset()
    his_words.note(w["stranger"])
    r = world.rec(f"s-{lang}")
    taint.mark(r, "recall:messages")
    out["stranger"] = _send(r, "Marcos Vidal")
    his_words.reset()
    from widgets.mensajeria import data
    data.apply_action("draft", {"contact": "quinn@example.com", "subject": "Thursday", "text": "Thursday at ten."})
    monkeypatch.setattr(his_words, "since", lambda ts: [w["send"]])          # his turn after the draft: he saw it
    quinn = {"contact": "quinn@example.com"}
    message.note_his_order("mensajeria", "send_draft", quinn,
                           _brief(screen_action=("mensajeria:send_draft", 0.95), request_type=("order", 1.0)))
    out["held"] = exit_gate.leave(world.rec(f"h-{lang}"), "widget_data",
                                  {"widget_id": "mensajeria", "action": "send_draft", "payload": quinn})
    return out


@pytest.mark.parametrize("lang", ["es", "en"])
def test_each_declared_slot_says_his_reading_held_or_a_stranger(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    ex = _scenes(world, lang, monkeypatch)
    assert ex["named"].slots["recipient"] == "his" and ex["named"].verdict == "pass", ex["named"]
    assert ex["stranger"].slots["recipient"] == "stranger" and ex["stranger"].verdict == "ask", ex["stranger"]
    assert ex["stranger"].payload["payload"]["contact"] == "Marcos Vidal"
    assert ex["channel"].payload["payload"]["channel"] == "whatsapp" and ex["channel"].slots["channel"] == "reading"
    assert ex["held"].released and ex["held"].verdict == "released", ex["held"]
    assert ex["held"].slots["draft"] == "held"
    # the record: each exit's event names each slot and its source
    by_id = {e["id"]: e for e in world.seen}
    assert by_id[f"s-{lang}"]["slots"]["recipient"] == "stranger"
    assert by_id[f"c-{lang}"]["slots"]["channel"] == "reading"
    assert by_id[f"h-{lang}"]["slots"]["draft"] == "held"


def test_the_slots_are_the_cards_declaration_and_a_row_call_is_the_cards():
    assert exit_slots.declared("mensajeria", "send_to") == {
        "recipient": {"key": "contact", "from": "his_words"}, "channel": {"key": "channel", "from": "reading"},
        "text": {"key": "text", "from": "composed"}}
    assert exit_slots.declared("mensajeria", "send_draft")["draft"]["from"] == "held"
    assert exit_slots.declared("agenda", "list_meetings") == {}
    import inspect
    src = inspect.getsource(exit_gate.gate)
    for reader in ("his_recipient", "his_channel", "message.confirmed", 'startswith("rows.")'):
        assert reader not in src, f"the door still names {reader}"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_disarmed_with_no_source_rule_the_slots_go_unread(world, lang, monkeypatch):
    monkeypatch.setattr(exit_slots, "RULES", {})
    assert exit_slots.declared("mensajeria", "send_to") == {}, "the disarm did not take"
    ex = _scenes(world, lang, monkeypatch)
    assert ex["channel"].payload["payload"]["channel"] == "telegram", "his channel did not go back in"
    # not released: the bridge's own CONFIRM of a `confirm: true` send asks him again
    assert not ex["held"].released and ex["held"].verdict != "released", "his order over the draft was not read"
    assert all(e.slots == {} for e in ex.values()) and all(e["slots"] == {} for e in world.seen)
