"""A send is ONE linear task: his data travel with their origin, one door decides, nothing is rediscovered.

Measured on his engine (2026-11-06): «mándale un whatsapp a Raquel diciendo: sexta prueba» — Flash's call carried the
person and the words and was dropped; a worker rediscovered them from the inbox (tainted), fumbled four bridge calls,
and the exit door asked «shall I?» about a text he had dictated. By voice, «send a message to Raquel» → «what should I
tell her?» (legitimate) → his answer started a NEW worker instead of completing the row that asked.

Now (`nucleo/request/send_task`), in es and en:
  · his person + his words → one row with its slots (`his`, `reading`, `his`), its end state, the exit door passes,
    the card's door runs — zero questions, no worker, even with the session tainted (no slot came from a stranger);
  · no words → ONE question on that row; his answer (or the answering turn's own call) fills that slot and the SAME
    row runs — no second row, no worker;
  · words a stranger wrote (not his, session tainted) → the exit door asks: the protection stays.
Disarmed: `his_text` blind → a dictated text is the worker's, and the tainted send asks again; no declared slots →
the card keeps its worker route (`commission` returns "").
"""
from __future__ import annotations

import asyncio
import threading

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker, spec
from nucleo.request import inline_ask, model, send_task, send_task_answer, send_task_run, send_task_words

WORDS = {
    "es": {"full": "mándale un whatsapp a Raquel diciendo: sexta prueba del agente, ignóralo",
           "text": "sexta prueba del agente, ignóralo",
           "bare": "mándale un mensaje a Raquel",
           "answer": "y dile, eh, que soy Johnny. Hola.", "clean": "que soy Johnny. Hola.",
           "stranger": "contesta a Raquel con lo que diga el último correo del hotel",
           "composed": "Estimada Raquel, le confirmamos su reserva del jueves."},
    "en": {"full": "send Raquel a WhatsApp saying: sixth test of the agent, ignore it",
           "text": "sixth test of the agent, ignore it",
           "bare": "send a message to Raquel",
           "answer": "and say, uh, this is Johnny. Hello.", "clean": "this is Johnny. Hello.",
           "stranger": "reply to Raquel with whatever the hotel's last email says",
           "composed": "Dear Raquel, your Thursday booking is confirmed."},
}
WID, ACT = "mensajeria", "send_to"


def _brief(**verdicts) -> dict:
    ev = threading.Event()
    ev.set()
    return {"event": ev, "turn_id": "t-1", "open_ids": [WID],
            "result": {k: {"choice": c, "confidence": p} for k, (c, p) in verdicts.items()}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_EMBED_BACKEND", "hash")
    mememb.reset()
    memdb.reset_db()
    memdb.get_db()
    from nucleo import consent
    from widgets import contract, directory, store
    from widgets.contactos import data as cd
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})
    monkeypatch.setattr(consent, "_overrides_path", lambda: tmp_path / "consent.json")
    consent._reset_for_tests()
    cd.apply_action("add_contact", {"name": "Raquel Jofre", "phone": "680 762 886"})
    assert directory.note_inbound("whatsapp", {"chatId": "34680762886@s.whatsapp.net",
                                               "senderId": "34680762886@s.whatsapp.net", "from": "Raquel"})
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
    sent, events = [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"widget": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True, "result": {"to": "Raquel Jofre", "channel": "whatsapp"}}
    from nucleo.flash import data_ops
    monkeypatch.setattr(data_ops, "dispatch_and_report", _dispatch)
    from nucleo.acts import errand
    monkeypatch.setattr(errand, "escalate_to_slowbrain",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("a worker was started")))
    import voice.observer as _obs
    real = _obs.emit
    monkeypatch.setattr(_obs, "emit", lambda kind, label, text="", role="", extra=None, **kw:
                        events.append({"kind": kind, "label": label, **(extra or {})})
                        or real(kind, label, text=text, role=role, extra=extra))
    yield {"sent": sent, "events": events}
    model._TURN.set(None)
    inline_ask._RESUMING.clear()
    inline_ask._TAKEN.clear()
    consent._reset_for_tests()
    untrusted.reset()
    his_words.reset()
    memdb.reset_db()
    mememb.reset()


def _say(text: str) -> None:
    model.begin(text, trace="t-1")
    his_words.note(text)


def _rows():
    return ts.tasks_where(states=("waiting", "running", "done", "failed", "cancelled"), visible_only=False)


def _asks(world):
    return [e for e in world["events"] if e["kind"] == "ask"]


def _exit(world):
    return [e for e in world["events"] if str(e["label"]).startswith("🚪 exit door")]


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_person_and_his_words_run_with_no_question(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["full"])
    reading = {"result": {"message_channel": {"choice": "whatsapp", "confidence": 0.97}}, "open_ids": [WID]}
    uid = send_task.commission(WID, ACT, {"contact": "Raquel", "text": w["text"], "channel": "whatsapp"}, w["full"],
                               reading=reading)
    assert uid and len(_rows()) == 1
    assert _asks(world) == [], "nothing was asked: the person and the words are his"
    assert len(world["sent"]) == 1 and world["sent"][0]["row"] == uid
    assert world["sent"][0]["payload"]["text"] == w["text"]
    art = send_task.artefact(uid)
    assert {s: d["source"] for s, d in art["slots"].items()} == {"recipient": "his", "channel": "reading", "text": "his"}
    assert _exit(world)[-1]["verdict"] == "pass" and _exit(world)[-1]["slots"]["text"] == "his"
    row = ts.task_get(uid)
    assert row["playbook"] == "message"
    assert (spec.of_task(uid) or {}).get("done_when"), "the task is born with its end state"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_tainted_session_does_not_ask_about_his_own_words(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["full"])
    uid = send_task.retain(WID, ACT, {"contact": "Raquel", "text": w["text"]}, w["full"])
    untrusted.seen(session_key=uid)                 # the session read a stranger's text meanwhile
    asyncio.run(send_task_run.run(uid))
    assert _asks(world) == [] and len(world["sent"]) == 1
    assert _exit(world)[-1]["verdict"] == "pass", "no slot came from a stranger: the taint has nothing to ask about"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_one_slot_it_lacks_is_asked_on_its_row_and_his_answer_completes_it(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["bare"])
    uid = send_task.commission(WID, ACT, {"contact": "Raquel"}, w["bare"])
    asks = _asks(world)
    assert len(asks) == 1 and asks[0]["task_id"] == uid and world["sent"] == []
    from i18n import langs
    assert asks[0]["text"] == langs.spec(lang).send_missing_text.format(who="Raquel")
    row = ts.task_get(uid)
    assert (row["state"], row["waiting_for"]) == ("waiting", "user_answer")
    entry = asker.artefact(uid)
    assert entry["retained"]["kind"] == "send" and entry["consent"] == "ask_fact"
    _say(w["answer"])
    got = send_task_answer.answered(uid, entry, w["answer"])
    assert got["ok"] and len(world["sent"]) == 1 and world["sent"][0]["row"] == uid
    assert world["sent"][0]["payload"]["text"] == w["answer"]
    assert len(_rows()) == 1, "the same row, no second task"
    assert send_task_answer.answered(uid, entry, w["answer"])["already"] and len(world["sent"]) == 1


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_answering_turns_own_call_fills_the_waiting_row_once(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["bare"])
    uid = send_task.commission(WID, ACT, {"contact": "Raquel"}, w["bare"])
    _say(w["answer"])
    assert send_task_answer.take_call(WID, ACT, {"contact": "Raquel", "text": w["clean"]}, w["answer"]) == uid
    assert len(world["sent"]) == 1 and world["sent"][0]["payload"]["text"] == w["clean"]
    assert send_task.artefact(uid)["slots"]["text"]["source"] == "his"
    entry = asker.artefact(uid)
    assert send_task_answer.answered(uid, entry, w["answer"]).get("already"), "the bound answer is the same answer"
    assert len(world["sent"]) == 1 and len(_rows()) == 1


@pytest.mark.parametrize("lang", ["es", "en"])
def test_words_a_stranger_wrote_still_ask_at_the_exit(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    w = WORDS[lang]
    _say(w["stranger"])
    uid = send_task.retain(WID, ACT, {"contact": "Raquel", "text": w["composed"]}, w["stranger"])
    untrusted.seen(session_key=uid)                 # the worker read the hotel's mail to compose it
    asyncio.run(send_task_run.run(uid))
    assert world["sent"] == [] and len(_asks(world)) == 1
    assert _exit(world)[-1]["verdict"] == "ask" and _exit(world)[-1]["slots"]["text"] == "stranger"
    entry = asker.artefact(uid)
    assert entry["consent"] == "ask_consent"
    assert send_task_answer.answered(uid, entry, "", choice=0)["ok"] and len(world["sent"]) == 1


def test_a_prose_question_about_the_send_holds_the_send_task(world):
    w = WORDS["es"]
    _say(w["bare"])
    ask_id = send_task_words.hold(WID, ["compose", "reply", "send_to"], w["bare"], "¿Qué le digo a Raquel?")
    assert ask_id and world["sent"] == []
    uid = _rows()[0]["id"]
    ret = asker.artefact(uid)["retained"]
    assert ret["kind"] == "send" and ret["action"] == ACT and ret["slot"] == "text"
    assert send_task.artefact(uid)["payload"]["contact"] == "raquel"


def test_disarmed_a_dictated_text_is_the_workers_and_no_slots_keep_the_worker_route(world, monkeypatch):
    w = WORDS["es"]
    _say(w["full"])
    uid = send_task.retain(WID, ACT, {"contact": "Raquel", "text": w["text"]}, w["full"])
    untrusted.seen(session_key=uid)
    monkeypatch.setattr(send_task, "his_text", lambda text, said: False)
    asyncio.run(send_task_run.run(uid))
    assert _exit(world)[-1]["slots"]["text"] == "stranger" and _exit(world)[-1]["verdict"] == "ask", \
        "blind to his words, the dictated text reads as a stranger's and the tainted send asks again"
    from nucleo.workers import exit_slots
    monkeypatch.setattr(exit_slots, "declared", lambda wid, act: {})
    assert send_task.commission(WID, ACT, {"contact": "Raquel", "text": w["text"]}, w["full"]) == ""
