"""V2-847 · an act that LEAVES the machine is «done» only when the world's echo of it lands — never on the queue's
word, never on a connector's note, never by having no condition at all.

Measured in a live session (mobile, 2026-11-04): «send Raquel a message saying I'm on my way» ran
`mensajeria:reply {n: 1, text}`. The card queued it (`ok: True`), the mouth read that as `met`, the request row was
settled `undeclared` — «It is done.» — because `reply` declared no end state, and the connector then pushed a note
«WhatsApp sent to <id>. Confirm it to the operator». Every one of those said «sent»; none of them had looked at what
left, or to whom. Four doors, one class: the claim did not come from a check against the world.

The mechanism, one door each:
  · a send declares its end state as a NEW row of what left (`expect: added` over `mensajeria.sent`, `queued` false),
    so an older message with the same words, or a row still in the queue, is not it;
  · the mouth reads a queued send as `started`, never `met` (`reply.of_op`);
  · an act that leaves with no end state to check is `unverifiable`, never `undeclared` (`data_ops`);
  · past the grace with no echo it is said as unconfirmed, not as failed (`circuit.tick`);
  · every action that declares `external.send` declares either its `done_when` or why it cannot have one.
"""
import asyncio
import json
import pathlib

import pytest

from memory import db as memdb
from memory import tasks_store as ts
from nucleo import circuit
from nucleo.circuit import spec, verify
from nucleo.request import model as rq

WIDGETS = pathlib.Path(__file__).resolve().parents[3] / "widgets"


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    memdb.reset_db(); memdb.get_db(); spec.reset()
    yield
    spec.reset(); memdb.reset_db()


class _Sent:
    """`mensajeria.sent` as a list the test writes: what left, and what is still queued."""

    def __init__(self, monkeypatch, rows=()):
        from widgets import rows as R
        self.rows = [dict(r) for r in rows]
        monkeypatch.setattr(R, "declared", lambda wid: {"sent": {"id": "id", "from": "view"}} if wid == "mensajeria"
                            else {})
        monkeypatch.setattr(R, "_rows", lambda wid, coll: list(self.rows) if (wid, coll) == ("mensajeria", "sent")
                            else [])

    def left(self, id_, body, name="Raquel"):
        self.rows.append({"id": id_, "body": body, "name": name, "chatId": "34600@s.whatsapp.net", "queued": False})

    def queued(self, id_, body, name="Raquel"):
        self.rows.append({"id": id_, "body": body, "name": name, "chatId": "34600@s.whatsapp.net", "queued": True})


# ── the grammar: a NEW row, not one like it ─────────────────────────────────────────────────────────────────────

def test_a_reply_is_born_with_the_end_state_of_a_new_message_that_left(monkeypatch):
    sent = _Sent(monkeypatch)
    sent.left("old-1", "Estoy de camino.")
    dw = spec.render("mensajeria", "reply", {"n": 1, "text": "estoy de camino"})
    assert dw["expect"] == "added" and dw["where"]["queued"] == "false"
    assert dw["baseline_ids"] == ["old-1"], "what already left is the baseline, taken at birth"
    assert verify.check(dw) is False, "last week's identical message is not the one he just asked for"
    sent.queued("ref-2", "estoy de camino")
    assert verify.check(dw) is False, "a row still in the queue has not left"
    sent.left("echo-3", "estoy de camino")
    assert verify.check(dw) is True


def test_the_same_holds_in_another_language_and_another_send(monkeypatch):
    sent = _Sent(monkeypatch)
    dw = spec.render("mensajeria", "send_to", {"contact": "Rowan", "text": "running late"})
    assert verify.check(dw) is False
    sent.queued("ref-1", "running late", name="Rowan")
    assert verify.check(dw) is False
    sent.left("echo-1", "running late", name="Rowan")
    assert verify.check(dw) is True


def test_a_row_that_cannot_be_named_reads_unverifiable_never_met(monkeypatch):
    sent = _Sent(monkeypatch)
    dw = spec.render("mensajeria", "reply", {"n": 1, "text": "hola"})
    sent.rows.append({"id": "", "body": "hola", "name": "Raquel", "queued": False})
    assert verify.check(dw) is None


def test_a_scheduled_send_is_done_when_it_is_scheduled(monkeypatch):
    sent = _Sent(monkeypatch)
    dw = spec.render("mensajeria", "send_draft", {"contact": "Rowan", "at": "21:00"})
    assert verify.check(dw) is False
    sent.rows.append({"id": "ref-9", "body": "hi", "name": "Rowan", "queued": True, "scheduled_for": 4102444800.0})
    assert verify.check(dw) is True


# ── the mouth: the queue taking it is not the receipt ──────────────────────────────────────────────────────────

def test_the_mouth_reads_a_queued_send_as_started_and_a_card_write_as_met():
    from nucleo.turn import reply as R
    assert R.of_op("mensajeria", "reply", {"ok": True}).verdict == "started"
    assert R.of_op("mensajeria", "send_to", {"ok": True, "title": "Rowan"}).verdict == "started"
    assert R.of_op("agenda", "add_meeting", {"ok": True, "title": "Dentist"}).verdict == "met"
    assert R.of_op("mensajeria", "reply", {"ok": False, "message": "no"}).verdict == "unmet"


# ── the door: no condition is not «done» for an act that leaves ─────────────────────────────────────────────────

def _run_door(monkeypatch, wid, action, payload):
    import widgets
    from nucleo.flash import data_ops

    async def dispatch(tag, body):
        return {"ok": True}

    async def nothing(*a, **k):
        return None
    monkeypatch.setattr(widgets, "dispatch_tag", dispatch)
    monkeypatch.setattr(spec, "open_for_action", lambda *a, **k: None)
    monkeypatch.setattr(data_ops, "report_failure", nothing)

    async def run():
        rq.begin("do it")
        await data_ops.dispatch_and_report(wid, action, payload, text="do it")
    asyncio.run(run())
    rows = [r for r in ts.tasks_where(states=ts.LIVE_STATES + ts.DONE_STATES, limit=10) if r["kind"] == "inline"]
    return rows[0]


def test_an_act_that_leaves_with_no_end_state_is_unverifiable(monkeypatch):
    row = _run_door(monkeypatch, "agenda", "invite", {"who": "Rowan", "meeting": "call"})
    assert row["verdict"] == "unverifiable"
    assert "calendar provider" in row["outcome"], "the declared reason travels with the row"


def test_an_act_that_stays_on_the_machine_with_no_end_state_stays_undeclared(monkeypatch):
    row = _run_door(monkeypatch, "agenda", "delete_meeting", {"title": "call"})
    assert row["verdict"] == "undeclared"


def test_a_refused_send_is_one_line_of_the_turn_and_no_model_runs_again(monkeypatch):
    """CRIT-E9c at the data door (V2-851 F2): a send the card REFUSES never left — its row ends `unmet`, the turn's
    mouth says the card's own sentence once (`reply.of_op`), and nothing after the stream asks a model to correct
    the call (the corrected re-call, its 🔔 and its note went). Disarm: a door that re-runs a model on a refusal, or
    says it out of turn while the turn is still waiting, goes red here."""
    import widgets
    from nucleo.flash import data_ops
    from nucleo.llm import fast_client
    from nucleo.pulse import notices
    from nucleo.turn import reply as R
    models, out_of_turn = [], []

    async def dispatch(tag, body):
        return {"ok": False, "message": "No encuentro a Raquel en tus chats."}

    async def complete(self, *a, **k):
        models.append(a)
        return ""

    async def notify(title, text, **k):
        out_of_turn.append(text)
        return {}
    monkeypatch.setattr(widgets, "dispatch_tag", dispatch)
    monkeypatch.setattr(spec, "open_for_action", lambda *a, **k: None)
    monkeypatch.setattr(fast_client.FastClient, "complete", complete)
    monkeypatch.setattr(notices, "notify", notify)

    async def run():
        rq.begin("tell Raquel I'm on my way")
        return await data_ops.dispatch_and_report("mensajeria", "send_to", {"contact": "Raquel", "text": "on my way"},
                                                  text="tell Raquel I'm on my way")
    res = asyncio.run(run())
    row = [r for r in ts.tasks_where(states=ts.LIVE_STATES + ts.DONE_STATES, limit=10) if r["kind"] == "inline"][0]
    assert row["verdict"] == "unmet", "a refused send never left the machine"
    assert models == [], "zero model re-runs after the stream (battery C6)"
    assert out_of_turn == [], "an answer in time is the turn's mouth's, never a second voice"
    lines = [t for _o, t in R.owed([R.of_op("mensajeria", "send_to", res)], "On it.")]
    assert len(lines) == 1 and "No encuentro a Raquel en tus chats." in lines[0], "one line, with the card's sentence"


# ── the pulse: no echo within the grace is unconfirmed, said now ───────────────────────────────────────────────

def test_a_send_with_no_echo_past_the_grace_is_said_unconfirmed_not_failed(monkeypatch):
    from nucleo.workers import spoken_delivery
    from voice import proactive
    _Sent(monkeypatch)
    summaries, said = [], []

    async def line(goal, summary, **k):
        summaries.append((summary, k.get("verdict")))
        return "I can't confirm it went out yet."

    async def notify(title, text, **k):
        said.append(text)
        return True
    monkeypatch.setattr(spoken_delivery, "line", line)
    monkeypatch.setattr(proactive, "notify", notify)

    async def run():
        rq.begin("tell Raquel I'm on my way")
        uid = rq.opened("mensajeria", "reply")
        dw = spec.render("mensajeria", "reply", {"n": 1, "text": "on my way"})
        e = spec.open(dw, text="x", source="flash", widget="mensajeria", action="reply", now=1000.0)
        e["row"], e["turn"] = uid, rq.current()
        circuit.tick(now=1000.0 + circuit.INLINE_GRACE_S)
        await asyncio.sleep(0.05)
        return uid
    uid = asyncio.run(run())
    assert ts.task_get(uid)["verdict"] == "unverifiable"
    assert summaries == [(circuit.UNCONFIRMED_SEND, "unverifiable")] and said == ["I can't confirm it went out yet."]


# ── the contract: every act that leaves says how it is checked ─────────────────────────────────────────────────

def _leaving_actions():
    out = []
    for m in sorted(WIDGETS.glob("*/manifest.json")):
        for action, spec_ in (json.loads(m.read_text(encoding="utf-8")).get("actions") or {}).items():
            if isinstance(spec_, dict) and "external.send" in (spec_.get("effects") or []):
                out.append((m.parent.name, action, spec_))
    return out


def test_there_are_acts_that_leave_to_check():
    assert {("mensajeria", "reply"), ("mensajeria", "send_to"), ("agenda", "invite")} <= {
        (w, a) for w, a, _ in _leaving_actions()}


@pytest.mark.parametrize("wid,action,spec_", _leaving_actions(), ids=lambda v: v if isinstance(v, str) else "")
def test_an_act_that_leaves_declares_how_it_is_checked(wid, action, spec_):
    dw, why = spec_.get("done_when"), str(spec_.get("done_when_unreadable") or "").strip()
    assert bool(dw) != bool(why), f"{wid}:{action} leaves the machine: declare `done_when` OR `done_when_unreadable`"


def test_a_send_whose_echo_lands_after_the_turn_is_said_sent(monkeypatch):
    """V2-850 — measured on his engine: «On it — I'll tell you when it's done», the WhatsApp echo landed, the check
    closed `met`… and nothing was said. The mouth read the queue as `started`; the echo is the moment to say «sent»."""
    from nucleo.workers import spoken_delivery
    from voice import proactive
    sent = _Sent(monkeypatch)
    lines, said = [], []

    async def line(goal, summary, **k):
        lines.append((summary, k.get("ok"), k.get("verdict")))
        return "Sent — Pablo has it."

    async def notify(title, text, **k):
        said.append(text)
        return True
    monkeypatch.setattr(spoken_delivery, "line", line)
    monkeypatch.setattr(proactive, "notify", notify)

    async def run():
        rq.begin("ask Pablo if he tried Zaelar")
        dw = spec.render("mensajeria", "send_to", {"contact": "Pablo", "text": "have you tried Zaelar?"})
        e = spec.open(dw, text="x", source="flash", widget="mensajeria", action="send_to", now=1000.0)
        e["row"], e["turn"] = rq.opened("mensajeria", "send_to"), rq.current()
        sent.left("echo-1", "have you tried Zaelar?", name="Pablo")
        circuit.tick(now=1000.0 + circuit.CHECK_EVERY_S + 1)
        await asyncio.sleep(0.05)
    asyncio.run(run())
    assert lines == [(circuit.SENT, True, "met")] and said == ["Sent — Pablo has it."]
