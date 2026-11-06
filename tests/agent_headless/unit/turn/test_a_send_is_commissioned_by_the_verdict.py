"""A send the brief identified is its task, whatever the model did instead of calling the door (2026-11-06).

Measured live (five cases, 0/5): the model never called `send_to` — it escalated a complete send (a worker
rediscovered it in 192 s, one exit-code-2 step), promised «Sending it now» with no call, asked «what should it say?» in
prose with no durable question, and on the answer turn the verdict completed the model with `dismiss`. Every time the
brief had already identified the send (`screen_action = mensajeria:send_to` 0.97-0.98, `end_state = mensajeria:sent`
0.82-0.92, `wants_words = act`), and every time the model had the words and QUOTED them.

So the turn's close and its escalation read the verdict (`send_task_words.by_verdict`): the person is his word, the
text is what the model quoted of his words (`quoted_his`: punctuation and his words, never a verb), the task runs with
no worker when every slot is his, waits on the one slot it lacks (the question the mouth already said becomes the
row's), or keeps the worker ON the row when the escalation lacked the words. A bound answer to a send task's question
is the words the model quoted of it. ES and EN; disarmed (`identified` blind) the verdict commissions nothing.
"""
from __future__ import annotations

import ast
import threading
from pathlib import Path

import pytest

from memory import db as memdb, embeddings as mememb, tasks_store as ts
from nucleo import his_words, untrusted
from nucleo.circuit import asker
from nucleo.request import inline_ask, model, send_task, send_task_words as stw

ROOT = Path(__file__).resolve().parents[4]
WID, ACT = "mensajeria", "send_to"
CASES = {
    "es": {"said": "mándale un correo a Andrew diciendo: prueba uno del envío lineal, ignóralo",
           "text": "prueba uno del envío lineal, ignóralo",
           "escalation": 'Send an email to Andrew (andrew@example.com) with exactly this body: "prueba uno del envío '
                         'lineal, ignóralo". Just send it, no reply expected.',
           "bare": "mándale un mensaje a Andrew", "prose_q": "¿Qué quieres que le diga, Richard?",
           "promise": 'Enviando ahora mismo «prueba uno del envío lineal, ignóralo» a Andrew.'},
    "en": {"said": "send Andrew an email saying: test two of the linear send, ignore it",
           "text": "test two of the linear send, ignore it",
           "escalation": 'Email Andrew the body "test two of the linear send, ignore it" and nothing else.',
           "bare": "send a message to Andrew", "prose_q": "What should it say, Richard?",
           "promise": 'Sending it now — same as before, just "test two of the linear send, ignore it" to Andrew.'},
}


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
    cd.apply_action("add_contact", {"name": "Andrew Gold", "email": "andrew@example.com"})
    cd.apply_action("add_contact", {"name": "Test Test", "email": "test@example.org"})      # a word of the dictated text
    cd.apply_action("add_contact", {"name": "Prueba Pérez", "email": "prueba@example.org"})
    monkeypatch.setattr(contract, "would_refuse", lambda *a, **k: None)
    untrusted.reset()
    his_words.reset()
    inline_ask._RECENT.clear()
    inline_ask._TAKEN.clear()
    inline_ask._RESUMING.clear()
    sent, events = [], []

    async def _dispatch(wid, action, payload, *, row="", text="", **kw):
        sent.append({"widget": wid, "action": action, "payload": dict(payload), "row": row})
        return {"ok": True, "result": {"to": "Andrew Gold", "channel": "email"}}
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
    yield {"sent": sent, "events": events, "emit": lambda *a, **k: events.append({"kind": a[0], "label": a[1], **(k.get("extra") or {})})}
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


SEND = dict(screen_action=(f"{WID}:{ACT}", 0.98), end_state=(f"{WID}:sent", 0.84), request_type=("order", 0.9),
            wants_words=("act", 0.98))


def test_the_brief_identifies_the_send_by_its_act_or_by_its_end_state():
    assert stw.identified(_brief(**SEND)) == (WID, ACT)
    assert stw.identified(_brief(screen_action=(f"{WID}:draft", 0.29), end_state=(f"{WID}:sent", 0.92))) == (WID, ACT)
    assert stw.identified(_brief(screen_action=(f"{WID}:show_view", 0.98))) == ("", "")
    assert stw.identified(_brief(end_state=("none", 0.9))) == ("", "")
    assert stw.identified(None) == ("", "")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_words_the_model_quoted_of_his_are_the_text(lang):
    c = CASES[lang]
    assert stw.quoted_his(c["said"], c["escalation"]) == c["text"]
    assert stw.quoted_his(c["said"], c["promise"]) == c["text"]
    assert stw.quoted_his(c["bare"], 'Sending "hello there" to Andrew now') == ""    # not his words
    assert stw.quoted_his(c["said"], "On it — emailing Andrew now.") == ""           # nothing quoted


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_escalation_that_quotes_his_words_runs_with_no_worker(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    c = CASES[lang]
    _say(c["said"])
    esc, acted = {"v": c["escalation"]}, {"v": None}
    uid, how = stw.by_verdict(_brief(**SEND), said=c["said"], model_text=esc["v"], escalate_req=esc,
                              worker_acted=acted, emit=world["emit"], on_missing="worker")
    assert uid and how == "run" and esc["send_task"]
    assert len(world["sent"]) == 1 and world["sent"][0]["payload"]["text"] == c["text"]
    assert send_task.artefact(uid)["slots"]["text"]["source"] == "his"
    assert _asks(world) == [] and len(_rows()) == 1


@pytest.mark.parametrize("lang", ["es", "en"])
def test_an_escalation_without_the_words_keeps_the_worker_on_the_rows_row(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    c = CASES[lang]
    _say(c["bare"])
    esc, acted = {"v": "Send Andrew a message; work out the wording from the conversation."}, {"v": None}
    uid, how = stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=esc["v"], escalate_req=esc,
                              worker_acted=acted, emit=world["emit"], on_missing="worker")
    assert uid and how == "worker" and world["sent"] == [] and _asks(world) == []
    row = ts.task_get(uid)
    assert row["playbook"] == "message" and send_task.artefact(uid)["slots"]["recipient"]["source"] == "his"
    assert stw.brief_block(uid), "the worker's brief carries the row's slots"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_promise_with_no_call_is_the_task_and_a_prose_question_is_the_rows(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    c = CASES[lang]
    _say(c["said"])
    esc, acted = {"v": None}, {"v": None}
    uid, how = stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"], escalate_req=esc,
                              worker_acted=acted, emit=world["emit"])
    assert how == "run" and len(world["sent"]) == 1 and world["sent"][0]["payload"]["text"] == c["text"]
    # the prose question: the row waits on IT, said once
    _say(c["bare"])
    esc = {"v": None}
    uid2, how2 = stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=c["prose_q"], escalate_req=esc,
                                worker_acted=acted, emit=world["emit"], asked_line=c["prose_q"])
    assert how2 == "asked" and uid2 != uid
    asks = _asks(world)
    assert len(asks) == 1 and asks[0]["text"] == c["prose_q"] and asks[0]["task_id"] == uid2
    assert ts.task_get(uid2)["state"] == "waiting" and len(world["sent"]) == 1


def test_a_turn_that_answered_a_task_or_already_retained_one_commissions_nothing(world):
    c = CASES["es"]
    _say(c["said"])
    assert stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"], escalate_req={"v": None},
                          worker_acted={"v": "answer"}, emit=world["emit"]) == ("", "")
    assert stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"],
                          escalate_req={"v": None, "send_task": True}, worker_acted={"v": None},
                          emit=world["emit"]) == ("", "")
    assert world["sent"] == [] and _rows() == []


def test_disarmed_a_blind_identification_commissions_nothing(world, monkeypatch):
    c = CASES["en"]
    _say(c["said"])
    monkeypatch.setattr(stw, "identified", lambda brief: ("", ""))
    assert stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"], escalate_req={"v": None},
                          worker_acted={"v": None}, emit=world["emit"]) == ("", "")
    assert world["sent"] == [] and _rows() == []


def _calls(path: str, attr: str) -> list:
    src = (ROOT / path).read_text(encoding="utf-8")
    return [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == attr]


def test_the_close_and_the_escalation_read_the_verdict_and_the_bound_answer_reads_the_quote():
    calls = _calls("nucleo/turn/pipeline_errands.py", "by_verdict")
    assert len(calls) == 2, "the escalation and the close each ask `by_verdict` once"
    esc = [c for c in calls if not any(kw.arg == "asked_line" for kw in c.keywords)][0]
    close = [c for c in calls if any(kw.arg == "asked_line" for kw in c.keywords)][0]
    assert {kw.arg: ast.unparse(kw.value) for kw in esc.keywords}.get("on_missing") == "'worker'"
    assert "ends_asking" in {kw.arg: ast.unparse(kw.value) for kw in close.keywords}["asked_line"]
    assert _calls("nucleo/flash/post_stream_settle.py", "quoted_his"), "the bound answer is the quoted text"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_the_person_is_never_read_from_the_words_he_dictated(world, lang, monkeypatch):
    """Measured live: «send Andrew an email saying: test six…» went to the contact «Test Test»."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    c = CASES[lang]
    _say(c["said"])
    uid, how = stw.by_verdict(_brief(**SEND), said=c["said"], model_text=c["promise"], escalate_req={"v": None},
                              worker_acted={"v": None}, emit=world["emit"])
    assert how == "run" and len(world["sent"]) == 1
    assert world["sent"][0]["payload"]["contact"].lower() == "andrew", world["sent"][0]["payload"]
    assert stw.without(c["said"], c["text"]).split()[-1] in ("saying", "diciendo")


@pytest.mark.parametrize("lang", ["es", "en"])
def test_his_quoted_words_complete_the_send_that_waited_for_them(world, lang, monkeypatch):
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    from nucleo.request import send_task_answer as sta
    c = CASES[lang]
    _say(c["bare"])
    uid, how = stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=c["prose_q"], escalate_req={"v": None},
                              worker_acted={"v": None}, emit=world["emit"], asked_line=c["prose_q"])
    assert how == "asked"
    answer = {"es": "dile: prueba siete, ignóralo", "en": "tell him: trial eight, ignore it"}[lang]
    quoted = {"es": "prueba siete, ignóralo", "en": "trial eight, ignore it"}[lang]
    _say(answer)
    # a quote of his words that does not name the waiting person completes nothing
    assert sta.fill_from_quote(answer, f'Searching for "{quoted}" on the web.', emit=world["emit"]) == ""
    assert world["sent"] == []
    assert sta.fill_from_quote(answer, f'Sending "{quoted}" to Andrew now.', emit=world["emit"]) == uid
    assert len(world["sent"]) == 1 and world["sent"][0]["payload"]["text"] == quoted and len(_rows()) == 1
    assert sta.fill_from_quote(answer, f'Sending "{quoted}" to Andrew now.', emit=world["emit"]) == ""


def test_a_spoken_answer_the_model_did_not_quote_is_composed_by_a_worker(world, monkeypatch):
    """Measured live: «contesta a Andrew con lo que diga el último correo de Inworld», bound as the answer to «what
    should it say?», was sent LITERALLY. An unquoted spoken answer goes to a worker on the row, which reads the mail
    (taint) — and the exit asks."""
    from nucleo.acts import errand
    from nucleo.request import send_task_answer as sta
    started = []
    monkeypatch.setattr(errand, "escalate_to_slowbrain", lambda req, *, context=None, task_id=0:
                        started.append((req, context)) or 9)
    c = CASES["es"]
    _say(c["bare"])
    uid, _how = stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=c["prose_q"], escalate_req={"v": None},
                               worker_acted={"v": None}, emit=world["emit"], asked_line=c["prose_q"])
    entry = asker.artefact(uid)
    line = "contesta a Andrew con lo que diga el último correo de Inworld"
    _say(line)
    sta.compose(entry["ask_id"])
    got = sta.answered(uid, entry, line)
    assert got.get("worker") == 9 and world["sent"] == []
    (req, ctx), = started
    assert ctx["task_uid"] == uid and ctx["playbook"] == "message" and line in req
    # disarmed (no compose mark): the same answer would have been sent literally
    _say(c["bare"])
    uid2, _ = stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=c["prose_q"], escalate_req={"v": None},
                             worker_acted={"v": None}, emit=world["emit"], asked_line=c["prose_q"])
    sta.answered(uid2, asker.artefact(uid2), line)
    assert world["sent"] and world["sent"][-1]["payload"]["text"] == line


def test_a_reply_whose_person_the_card_picks_is_never_commissioned_by_the_verdict(world):
    """Measured live: «contesta a Andrew con lo que diga el último correo de Inworld» → verdict `mensajeria:reply`,
    a reply row with no person and no text waited on «What should I tell ??» — any answer bound to it would have
    answered the last inbound mail. Only an act whose person comes from HIS words is the verdict's; with `reply` named
    the end state's own send stands (send_to, the person his word), and his words naming nobody commission nothing."""
    assert stw.identified(_brief(screen_action=(f"{WID}:reply", 0.53))) == ("", "")
    assert stw.identified(_brief(screen_action=(f"{WID}:reply", 0.53), end_state=(f"{WID}:sent", 0.92))) == (WID, ACT)
    _say("contesta con lo que diga el último correo del hotel")
    assert stw.by_verdict(_brief(screen_action=(f"{WID}:reply", 0.6), end_state=(f"{WID}:sent", 0.92)),
                          said="contesta con lo que diga el último correo del hotel", model_text="",
                          escalate_req={"v": None}, worker_acted={"v": None}, emit=world["emit"]) == ("", "")
    assert world["sent"] == [] and _rows() == [] and _asks(world) == []


def test_a_sure_escalate_at_the_close_composes_on_the_send_row():
    calls = _calls("nucleo/turn/pipeline_errands.py", "by_verdict")
    close = [c for c in calls if any(kw.arg == "asked_line" for kw in c.keywords)][0]
    kw = {k.arg: ast.unparse(k.value) for k in close.keywords}
    assert "escalate" in kw["on_missing"], "a sure escalate verdict at the close hands the row to a worker"


@pytest.mark.parametrize("lang", ["es", "en"])
def test_a_sure_escalate_never_runs_the_send_inline(world, lang, monkeypatch):
    """Measured live: «busca en mi correo el último de Inworld y mándale a Andrew lo que diga» (escalate 0.72) ran
    inline as a send with the word «Inworld» as his text. Work is composed by the worker on the row."""
    monkeypatch.setenv("ZAELAR_LANGUAGE", lang)
    said = {"es": "busca el último correo del hotel y mándale a Andrew lo que diga",
            "en": "find the hotel's last email and send Andrew what it says"}[lang]
    _say(said)
    uid, how = stw.by_verdict(_brief(**SEND, escalate_or_inline=("escalate", 0.72)), said=said,
                              model_text='Find the "hotel" email and send Andrew what it says.',
                              escalate_req={"v": "x"}, worker_acted={"v": None}, emit=world["emit"])
    assert how == "worker" and uid and world["sent"] == [] and _asks(world) == []


def test_a_new_send_to_his_named_person_answers_no_stale_question(world):
    c = CASES["en"]
    _say(c["bare"])
    stw.by_verdict(_brief(**SEND), said=c["bare"], model_text=c["prose_q"], escalate_req={"v": None},
                   worker_acted={"v": None}, emit=world["emit"], asked_line=c["prose_q"])
    asks = [{"task_id": "stale-1", "ask_id": "stale-1-q1"}]   # a waiting row that is no send to Andrew
    assert stw.new_send(_brief(**SEND), c["said"], asks) is True
    waiting = [{"task_id": r["id"], "ask_id": r["ask_id"]} for r in _rows() if r["state"] == "waiting"]
    assert stw.new_send(_brief(**SEND), c["said"], waiting) is False, "a send to Andrew already waits: it may be his answer"
    assert stw.new_send(_brief(screen_action=(f"{WID}:show_view", 0.9)), c["said"], asks) is False


def test_a_turn_that_is_its_own_send_task_answers_no_other_waiting_question(world, monkeypatch):
    """Measured live: the turn opened its send task AND a 0.51 reading bound the same words to a stale reply row, which
    then tried to send. A turn whose words already are a send task binds nothing else; disarmed, the stale row binds."""
    from nucleo.cli import worker_api, worker_api_bind as bind
    from nucleo.flash import post_stream_settle as pss
    stale = [{"task_id": "stale-1", "ask_id": "stale-1-q3"}]
    monkeypatch.setattr(bind, "bind", lambda brief, **k: (bind.ANSWER, stale))
    taken = []
    monkeypatch.setattr(worker_api, "answer_soon", lambda ask_id, *a, **k: taken.append(ask_id) or True)

    def _run(req):
        return pss.bind_the_answer(_brief(**SEND), CASES["es"]["said"], model_answer="", worker_acted={"v": None},
                                   escalate_req=req, others_acted=False, spoken_text="x", send=lambda *_: None,
                                   speech=None, emit=world["emit"])
    _run({"v": None, "send_task": True})
    assert taken == [], "his words are this turn's send task: the stale row is not answered"
    _run({"v": None})
    assert taken == ["stale-1-q3"], "disarmed (no send task this turn), the binding still works"
