"""V2-771 — a message that hands over several tasks is a LIST: detected, split, stored, run step by step, reported.

Measured before (2026-09-25): the operator's 12-section setup message was ONE turn, and six per-turn limits each
dropped part of it without a word — the input clamp kept its last 1 600 chars, the memory distiller read its
first 600, five widget writes, three workers, and the rename lane took a one-line paste whole.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest

from nucleo import batch
from nucleo.batch import detect, runner, split

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _no_settle(monkeypatch):
    """No real dispatcher here: nothing registers late, so a step does not wait for it."""
    monkeypatch.setattr(runner, "_SETTLE_S", 0.0)

LIST = "\n".join([
    "SETUP", "Do these in order.", "",
    "1. IDENTITY", "Your name is Johnny.", "",
    "2. PROFILE", "Remember: my name is Richard. I live in Los Angeles. I work in AI.", "",
    "3. CALENDAR", "Create an event on September 28, 2026 from 9:00 to 9:30: ZAELAR weekly review.", "",
    "4. BEHAVIOUR", "When I ask you to organize something, do as much as possible instead of explaining.",
    "Do not ask me for information already stored in memory unless it is genuinely missing.",
])


# ── detect ───────────────────────────────────────────────────────────────────────────────────────────────
def test_a_short_request_never_asks_anybody(monkeypatch):
    def _boom(*a, **k):
        raise AssertionError("Jev must not be asked below the shape floor")
    monkeypatch.setattr("nucleo.jev.choose_sync", _boom)
    assert asyncio.run(detect.is_a_list("Apúntame el dentista el jueves a las diez y llama a Pedro")) == (False, {"by": "shape"})
    # short, but shaped like a list: still below the floor — a short message is one turn whatever its shape
    assert asyncio.run(detect.is_a_list("1. pan\n2. leche\n3. huevos\n4. fruta. Y ya.")) == (False, {"by": "shape"})


def test_past_the_floor_jev_decides_in_both_directions(monkeypatch):
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: {"choice": "several", "confidence": 0.93})
    assert asyncio.run(detect.is_a_list(LIST))[0] is True
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: {"choice": "single", "confidence": 0.95})
    assert asyncio.run(detect.is_a_list(LIST))[0] is False
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: {"choice": "several", "confidence": 0.5})
    assert asyncio.run(detect.is_a_list(LIST))[0] is False          # an unsure «several» stays one turn


def test_without_jev_only_an_unmistakable_shape_is_a_list(monkeypatch):
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: None)
    assert asyncio.run(detect.is_a_list(LIST)) == (True, {"by": "shape-fallback"})
    long_single = "Busca un piso en Madrid, " + ", ".join(f"condición {i}" for i in range(80)) + "."
    assert detect.could_be_a_list(long_single) and asyncio.run(detect.is_a_list(long_single))[0] is False


# ── split ────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_split_reads_fenced_json_and_refuses_garbage():
    got = split.parse('```json\n{"steps": [{"title": "a", "kind": "agenda", "say": "Create X"}, '
                      '{"kind": "weird", "say": "Remember Y"}]}\n```')
    assert [s["say"] for s in got] == ["Create X", "Remember Y"] and got[1]["kind"] == "other"
    assert split.parse("sorry, I cannot") == [] and split.parse('{"steps": "nope"}') == []


def test_an_oversized_step_is_split_at_sentences_and_loses_nothing():
    """Measured on his demo: one 700-char «DEFAULT BEHAVIOR» step cut at 560 dropped its last line."""
    long = " ".join(f"Rule number {i} says do the thing properly." for i in range(20)) + \
        " Do not ask me for information already stored in memory."
    got = split.parse('{"steps": [{"title": "rules", "kind": "rule", "say": "%s"}]}' % long)
    assert len(got) >= 2 and all(len(s["say"]) <= split.MAX_STEP_CHARS for s in got)
    assert "Do not ask me for information already stored in memory." in got[-1]["say"]
    assert " ".join(s["say"] for s in got) == long


def test_a_failed_model_falls_to_the_message_own_sections():
    steps, how = split.split(LIST, chat=lambda *a, **k: None)
    assert how == "sections" and len(steps) == 4 and steps[0]["say"].startswith("IDENTITY")
    steps, how = split.split("just one thing, really", chat=lambda *a, **k: None)
    assert (steps, how) == ([], "none")


def test_the_model_split_is_used_when_it_has_two_steps_or_more():
    ans = '{"steps": [{"title": "t1", "kind": "identity", "say": "Your name is Johnny."}, ' \
          '{"title": "t2", "kind": "memory", "say": "Remember: I live in Los Angeles."}]}'
    steps, how = split.split(LIST, chat=lambda *a, **k: ans)
    assert how == "model" and [s["kind"] for s in steps] == ["identity", "memory"]


# ── the runner ───────────────────────────────────────────────────────────────────────────────────────────
STEPS = [{"title": "name", "kind": "identity", "say": "Your name is Johnny."},
         {"title": "fact", "kind": "memory", "say": "Remember: I live in Los Angeles."},
         {"title": "search", "kind": "task", "say": "Find me a hotel in Soria."},
         {"title": "ask", "kind": "agenda", "say": "Book the usual."},
         {"title": "broken", "kind": "agenda", "say": "Create the event."}]


def _replies():
    return {"Your name is Johnny.": {"ok": True, "reply": ["Done."]},
            "Remember: I live in Los Angeles.": {"ok": True, "reply": ["Noted."]},
            "Find me a hotel in Soria.": {"ok": True, "reply": ["On it."], "executed": "escalate",
                                          "task_ids": ["7"]},
            "Book the usual.": {"ok": True, "reply": ["Which one do you mean?"]},
            "Create the event.": {"ok": True, "reply": ["Hecho."], "executed": "widget_data_failed"}}


def _run(uid, *, workers=None, calls=None, ingested=None, notes=None):
    replies = _replies()
    calls = [] if calls is None else calls
    ingested = [] if ingested is None else ingested
    notes = [] if notes is None else notes

    async def turn(text, **kw):
        calls.append((text, kw))
        return replies[text]

    async def ingest(text):
        await asyncio.sleep(0)
        ingested.append(text)

    async def notify(title, text):
        notes.append(text)
    return asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=notify, worker_wait_s=0.2))


def test_a_list_runs_every_step_in_order_as_an_ordinary_turn_and_reports_once(monkeypatch):
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    uid = runner.create("the whole message", STEPS, origin="chat")
    calls, ingested, notes = [], [], []
    s = _run(uid, calls=calls, ingested=ingested, notes=notes)
    assert [c[0] for c in calls] == [x["say"] for x in STEPS]
    # every step is a turn that EXECUTES, never re-read as a list, memory written by the list itself
    assert all(kw == {"sid": uid, "ingest": False, "execute": True, "lists": False} for _, kw in calls)
    assert ingested == [x["say"] for x in STEPS]
    assert len(s["done"]) == 3 and [r["title"] for r in s["failed"]] == ["broken"]
    assert [r["title"] for r in s["needs_you"]] == ["ask"]
    assert len(notes) == 1
    assert "3" in notes[0] and "5" in notes[0] and "broken" in notes[0] and "Which one" in notes[0]
    row = batch.status(uid)["list"]
    assert row["kind"] == "lista" and row["visible"] and row["state"] == "failed"
    assert all(not st["visible"] for st in batch.status(uid)["steps"])


def test_the_report_waits_for_the_workers_the_list_started(monkeypatch):
    """«I've finished» over a worker still running is the claim V2-743 forbids."""
    monkeypatch.setattr(runner, "_POLL_S", 0.01)
    seen = {"n": 0}

    def worker_state(tid):
        seen["n"] += 1
        return "done" if seen["n"] >= 3 else ""        # alive for two polls, then finished
    monkeypatch.setattr(runner, "_worker_state", worker_state)
    uid = runner.create("msg", STEPS[:3])
    notes = []
    s = _run(uid, notes=notes)
    assert seen["n"] >= 3 and [r["title"] for r in s["done"]] == ["name", "fact", "search"]
    assert notes and "3" in notes[0]


def test_a_worker_that_outlives_the_wait_is_named_and_the_list_still_closes(monkeypatch):
    monkeypatch.setattr(runner, "_POLL_S", 0.01)
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "")
    uid = runner.create("msg", STEPS[:3])
    notes = []
    s = _run(uid, notes=notes)
    assert [r["title"] for r in s["running"]] == ["search"]
    assert batch.status(uid)["list"]["state"] == "done"      # closed once reported, never re-run at boot


def test_a_restart_resumes_from_the_first_unfinished_step(monkeypatch):
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    monkeypatch.setattr(runner, "RESUME_DELAY_S", 0.0)
    uid = runner.create("msg", STEPS[:2])
    ts = runner._store()
    first, second = runner.steps_of(uid)
    ts.task_patch(first["id"], state="done", outcome="[done] ok")
    ts.task_patch(second["id"], state="running")          # the restart hit mid-turn: nothing claims it
    ts.task_patch(uid, state="running")
    calls = []

    async def turn(text, **kw):
        calls.append(text)
        return {"ok": True, "reply": ["ok"]}

    async def ingest(text):
        return None

    async def notify(title, text):
        return None

    real_run = runner.run
    monkeypatch.setattr(runner, "run", lambda u: real_run(u, turn=turn, ingest=ingest, notify=notify,
                                                           worker_wait_s=0.1))

    async def _go():
        got = runner.resume()
        await asyncio.sleep(0.3)
        return got
    assert asyncio.run(_go()) == [uid]
    assert calls == [STEPS[1]["say"]]


def test_the_step_outcome_is_read_from_the_turn_itself():
    assert runner.outcome_of({"ok": False, "error": "model down"})[0] == "failed"
    assert runner.outcome_of({"ok": True, "reply": ["Hecho."], "executed": "widget_data_failed"})[0] == "failed"
    assert runner.outcome_of({"ok": True, "reply": ["Vale."], "task_id": "3"}) == ("waiting", "Vale.", ["3"])
    assert runner.outcome_of({"ok": True, "reply": ["¿Cuál de las dos?"]})[0] == "needs_you"
    assert runner.outcome_of({"ok": True, "reply": ["Apuntado."]})[0] == "done"
    # an escalation the portal refused (id 0): no errand was born, so the step did not happen
    assert runner.outcome_of({"ok": True, "reply": "Voy a por ellas.", "executed": "escalate",
                              "task_id": 0, "task_ids": [0]})[0] == "failed"


# ── the door ─────────────────────────────────────────────────────────────────────────────────────────────
def test_the_door_answers_with_one_line_and_starts_the_list_in_the_background(monkeypatch):
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: {"choice": "several", "confidence": 0.99})
    started = []

    async def fake_start(text, **kw):
        started.append((text, kw))
        return "lista:x"
    monkeypatch.setattr(batch, "start", fake_start)

    async def _go():
        got = await batch.intake(LIST, origin="chat")
        await asyncio.sleep(0)
        return got
    got = asyncio.run(_go())
    assert got == {"ack": batch.ack()} and started == [(LIST, {"origin": "chat"})]
    assert "{" not in got["ack"] and LIST[:20] not in got["ack"]           # the receipt never reads it back
    assert asyncio.run(batch.intake("hola, ¿qué tal?")) is None


def test_a_list_that_cannot_be_split_is_still_run_as_one_step(monkeypatch):
    monkeypatch.setattr(split, "split", lambda text, **k: ([], "none"))
    uid = asyncio.run(batch.start("a long message", run=False))
    steps = batch.status(uid)["steps"]
    assert len(steps) == 1 and steps[0]["goal"] == "a long message"


# ── wiring: the list goes FIRST in both channels ─────────────────────────────────────────────────────────
def test_both_channels_ask_about_a_list_before_any_other_lane():
    voice = (ROOT / "voice/engine/llm/providers/nucleo.py").read_text()
    i_list, i_rename, i_clamp = (voice.index("_fast_lane.task_list("), voice.index("_fast_lane.rename("),
                                 voice.index("attention.clamp_input("))
    i_handled = voice.index("_fast_lane.handled(")
    assert i_list < i_handled < i_rename < i_clamp
    probe = (ROOT / "nucleo/flash/probe.py").read_text()
    assert probe.index("await _task_list(text, sess)") < probe.index("_lane = _fast_lanes(text, sess")
    assert "lists=False" in (ROOT / "nucleo/batch/runner.py").read_text()


# ── what the list exposed ────────────────────────────────────────────────────────────────────────────────
def test_an_end_date_with_no_rule_is_every_day_of_the_stretch():
    from widgets.agenda import recur
    rep, err = recur.parse({"date": "2026-12-20", "endDate": "2027-01-04"}, "2026-12-20")
    assert err == "" and rep["freq"] == "daily" and rep["until"] == "2027-01-04"
    m = {"date": "2026-12-20", "repeat": rep}
    assert len(recur.occurrences(m, "2026-12-01", "2027-01-31")) == 16
    rep, _ = recur.parse({"date": "2026-09-29", "until": "2026-12-31", "days": "martes"}, "2026-09-29")
    assert rep["freq"] == "weekly" and rep["days"] == [1]


def test_two_workers_at_a_time_is_the_default(monkeypatch):
    """«Dos tareas a la vez, el resto en cola» — in all three places the number lives."""
    from config import v2
    from nucleo import dispatch
    monkeypatch.delenv("CODE_AGENT_MAX_PARALLEL", raising=False)
    assert v2._DEFAULTS["code_agent"]["max_parallel"] == 2
    monkeypatch.setattr(v2, "get", lambda section: {})
    assert dispatch._max_parallel() == 2                    # a config without the key

    def _broken(section):
        raise RuntimeError("config unreadable")
    monkeypatch.setattr(v2, "get", _broken)
    assert dispatch._max_parallel() == 2                    # no config at all
    monkeypatch.setenv("CODE_AGENT_MAX_PARALLEL", "4")
    assert dispatch._max_parallel() == 4                    # the operator's override still wins


@pytest.mark.parametrize("field", ["list_started", "list_done", "list_failed", "list_needs_you",
                                   "list_still_running"])
def test_every_list_line_exists_in_spanish_and_english(field):
    from i18n import langs
    es, en = langs.LANGUAGES["es"], langs.LANGUAGES["en"]
    assert getattr(es, field) and getattr(en, field) and getattr(es, field) != getattr(en, field)


def test_the_text_channel_receipt_is_a_string_like_every_other_reply(monkeypatch):
    """Measured in the first live run: a list-shaped `reply` reached the harness as an empty line."""
    from types import SimpleNamespace

    from nucleo.flash import probe

    async def fake_intake(text, **kw):
        return {"ack": "Got it."}
    monkeypatch.setattr(batch, "intake", fake_intake)
    sess = SimpleNamespace(window=[])
    got = asyncio.run(probe._task_list(LIST, sess))
    assert got["reply"] == "Got it." and got["action"] == "task_list"
    assert sess.window[-1] == {"role": "assistant", "content": "Got it."}


def test_a_courtesy_question_is_not_a_step_that_needs_him(monkeypatch):
    """First live run: «Noted… Anything you want me to dig up?» — DONE, reported as needing him because the
    reply ended in «?». Jev reads what the question is for; unsure or silent keeps the honest side."""
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    verdicts = {"Which one do you mean?": {"choice": "needs_answer", "confidence": 1.0},
                "Noted. Anything else?": {"choice": "done", "confidence": 0.99}}
    monkeypatch.setattr("nucleo.jev.choose_sync",
                        lambda key, state, **k: verdicts.get(state.split("REPLY: ", 1)[1]))
    assert asyncio.run(runner.reply_needs_him("Book the usual.", "Which one do you mean?")) is True
    assert asyncio.run(runner.reply_needs_him("Remember X.", "Noted. Anything else?")) is False
    assert asyncio.run(runner.reply_needs_him("Remember X.", "Something unknown?")) is True          # no verdict
    monkeypatch.setattr("nucleo.jev.choose_sync", lambda *a, **k: {"choice": "done", "confidence": 0.5})
    assert asyncio.run(runner.reply_needs_him("Remember X.", "Noted. Anything else?")) is True        # unsure

    monkeypatch.setattr("nucleo.jev.choose_sync",
                        lambda key, state, **k: verdicts.get(state.split("REPLY: ", 1)[1]))
    uid = runner.create("msg", [{"title": "fact", "kind": "memory", "say": "Remember X."},
                                {"title": "ask", "kind": "agenda", "say": "Book the usual."}])
    replies = {"Remember X.": {"ok": True, "reply": "Noted. Anything else?"},
               "Book the usual.": {"ok": True, "reply": "Which one do you mean?"}}

    async def turn(text, **kw):
        return replies[text]

    async def nothing(*a, **k):
        return None
    s = asyncio.run(runner.run(uid, turn=turn, ingest=nothing, notify=nothing, worker_wait_s=0.1))
    assert [r["title"] for r in s["done"]] == ["fact"] and [r["title"] for r in s["needs_you"]] == ["ask"]


def test_an_action_step_whose_turn_did_nothing_is_retried_once_then_failed(monkeypatch):
    """Second live run: «Create a calendar event …» → «I'll put that on your agenda now.» and NO call, twice in
    seven; the list counted both DONE. The turn's report says whether it acted, never its words."""
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    uid = runner.create("msg", [{"title": "fact", "kind": "memory", "say": "Remember X."},
                                {"title": "lunch", "kind": "agenda", "say": "Create lunch."},
                                {"title": "vet", "kind": "agenda", "say": "Create vet."}])
    calls = []

    async def turn(text, **kw):
        calls.append((text, kw["sid"]))
        if text == "Create lunch." and kw["sid"] != uid:           # the retry, in a fresh session, acts
            return {"ok": True, "reply": "Done.", "action": "widget_data", "tool_calls": [{"name": "widget_data"}]}
        return {"ok": True, "reply": "Adding it now.", "action": "chat", "tool_calls": []}

    async def nothing(*a, **k):
        return None
    s = asyncio.run(runner.run(uid, turn=turn, ingest=nothing, notify=nothing, worker_wait_s=0.1))
    assert [c[0] for c in calls] == ["Remember X.", "Create lunch.", "Create lunch.", "Create vet.", "Create vet."]
    assert calls[1][1] == uid and calls[2][1] != uid                # the retry does not read its own claim
    assert [r["title"] for r in s["done"]] == ["fact", "lunch"] and [r["title"] for r in s["failed"]] == ["vet"]
    assert "no action taken" in runner.steps_of(uid)[2]["outcome"]
    assert runner.acted({"action": "rename"}) and not runner.acted({"action": "chat", "reply": "Hecho."})


def test_a_reminder_step_that_was_remembered_is_done_but_an_agenda_step_still_needs_its_call(monkeypatch):
    """His demo run (2026-09-26): «Remember these future responsibilities even when they are not on the calendar:
    Tesla insurance renewal: March 12, 2027…» was split as `reminder`, the four renewals landed in memory, and
    the step was failed «no action taken» — the report told him «I couldn't do: Personal reminders». For a
    reminder, remembering IS the action; for an agenda entry it never is."""
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    uid = runner.create("msg", [{"title": "renewals", "kind": "reminder", "say": "Remember the renewals."},
                                {"title": "vet", "kind": "agenda", "say": "Create vet."}])

    async def turn(text, **kw):
        return {"ok": True, "reply": "Noted.", "action": "chat", "tool_calls": []}

    async def ingest(text):
        return {"source": "processor", "atoms": 4}          # memory wrote for BOTH steps

    async def nothing(*a, **k):
        return None
    s = asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=nothing, worker_wait_s=0.1))
    assert [r["title"] for r in s["done"]] == ["renewals"], s
    assert [r["title"] for r in s["failed"]] == ["vet"], "a calendar entry is never «done» by remembering it"


def test_a_relayed_worker_is_over_when_its_durable_row_says_so(monkeypatch):
    """Errands case: worker 1 was relayed to another provider (new id 3, same row). Its RAM record stays
    `relevada` for good; the row said `failed` — the list must read the row, not wait 45 minutes."""
    from types import SimpleNamespace

    from nucleo import dispatch, tasks as _tasks
    ts = runner._store()
    monkeypatch.setattr(dispatch, "get_record", lambda tid: SimpleNamespace(status="relevada"))
    ts.task_put({"id": _tasks.task_uid("91"), "title": "x", "state": "running"})
    assert runner._worker_state("91") == ""                       # row open, relay still working
    ts.task_patch(_tasks.task_uid("91"), state="failed")
    assert runner._worker_state("91") == "failed"                 # the row closed: over, whatever RAM says
    monkeypatch.setattr(dispatch, "get_record", lambda tid: None)
    assert runner._worker_state("does-not-exist") == "done"       # a ghost is never waited on


def test_a_list_step_never_drains_the_operators_notes():
    """Errands case: the step after a refused search swallowed the refusal note meant for him and answered
    about it. `lists=False` (a step) must leave `brain_notes` for his next turn."""
    src = (ROOT / "nucleo/flash/probe.py").read_text()
    assert "_notes = _bn.drain() if lists else []" in src


def test_a_worker_a_step_started_by_another_door_is_still_waited_for(monkeypatch):
    """Errands case: a product search went through the listings lane, which starts its worker inside and
    reports only its words — the step read DONE and the report would have gone out over a live worker."""
    monkeypatch.setattr(runner, "_SETTLE_S", 0.0)
    monkeypatch.setattr(runner, "_POLL_S", 0.01)
    live = {"ids": {}}
    monkeypatch.setattr(runner, "_live_workers", lambda: dict(live["ids"]))
    finished = {"n": 0}

    def state(tid):
        finished["n"] += 1
        return "done" if finished["n"] >= 3 else ""
    monkeypatch.setattr(runner, "_worker_state", state)
    uid = runner.create("msg", [{"title": "shoes", "kind": "task", "say": "Find trail shoes."}])

    async def turn(text, **kw):
        live["ids"]["u-17"] = "17"                     # the lane started a worker and said nothing about it
        return {"ok": True, "reply": "Voy a buscarlas.", "action": "listings"}

    async def nothing(*a, **k):
        return None
    s = asyncio.run(runner.run(uid, turn=turn, ingest=nothing, notify=nothing, worker_wait_s=1))
    assert "workers:17" in runner.steps_of(uid)[0]["outcome"] and finished["n"] >= 3
    assert [r["title"] for r in s["done"]] == ["shoes"]


def test_a_relay_of_another_steps_worker_is_not_this_steps_worker(monkeypatch):
    """Run 4: the trainers search was relayed (new worker id, SAME commission uid) while the restaurant step ran;
    the restaurant step had only SAID «voy con el restaurante» and was counted as waiting on that worker."""
    from nucleo import dispatch
    sessions = [{"id": 1, "uid": "b-1"}]
    monkeypatch.setattr(dispatch, "active_sessions", lambda: list(sessions))
    before = runner._live_workers()
    sessions[:] = [{"id": 2, "uid": "b-1"}]            # the relay: new id, inherited uid
    after = runner._live_workers()
    assert set(after) - set(before) == set()
    sessions.append({"id": 3, "uid": "b-3"})           # a genuinely new commission
    assert [runner._live_workers()[k] for k in set(runner._live_workers()) - set(before)] == ["3"]


def test_five_errands_never_run_more_than_two_at_a_time(monkeypatch):
    """«Si nos encargan seis tareas complejas, no hace falta abrir seis brain workers a la vez… dos a la vez, el
    resto en cola.» Measured on the dispatcher's REAL semaphore — the one `_run_session` enters — not on the
    number in the config: five sessions, at most two inside, and all five finish (queued, not dropped)."""
    from nucleo import dispatch
    monkeypatch.delenv("CODE_AGENT_MAX_PARALLEL", raising=False)
    monkeypatch.setattr("config.v2.get", lambda section: {})
    monkeypatch.setattr(dispatch, "_sem", None)
    inside = {"now": 0, "max": 0, "done": 0}

    async def session():
        async with dispatch._pool():
            inside["now"] += 1
            inside["max"] = max(inside["max"], inside["now"])
            await asyncio.sleep(0.01)
            inside["now"] -= 1
            inside["done"] += 1

    async def _go():
        await asyncio.gather(*(session() for _ in range(5)))
    asyncio.run(_go())
    monkeypatch.setattr(dispatch, "_sem", None)
    assert inside == {"now": 0, "max": 2, "done": 5}
    src = (ROOT / "nucleo/dispatch.py").read_text()
    assert "async with _pool():" in src            # the gate every worker session passes through


def test_a_timed_alert_that_was_only_remembered_is_not_done(monkeypatch):
    """V2-773 audit: «Remind me on Friday at 9 to call the vet» is an ALARM. Memory writing an atom about it is
    not the alarm — reported done, nothing would ever ring. The reminder exemption is for facts to keep
    («remember that the insurance renews…») that the split still labels `reminder`."""
    monkeypatch.setattr(runner, "_worker_state", lambda tid: "done")
    uid = runner.create("msg", [{"title": "vet call", "kind": "reminder",
                                 "say": "Remind me on Friday at 9 to call the vet."},
                                {"title": "renewals", "kind": "reminder",
                                 "say": "Remember that the Tesla insurance renews on March 12, 2027."}])

    async def turn(text, **kw):
        return {"ok": True, "reply": "Noted.", "action": "chat", "tool_calls": []}

    async def ingest(text):
        return {"source": "processor", "atoms": 1}

    async def nothing(*a, **k):
        return None
    s = asyncio.run(runner.run(uid, turn=turn, ingest=ingest, notify=nothing, worker_wait_s=0.1))
    assert [r["title"] for r in s["failed"]] == ["vet call"], s
    assert [r["title"] for r in s["done"]] == ["renewals"], s
    for said in ("recuérdame el viernes a las 9", "avísame mañana", "set a reminder for 5pm", "wake me at 7"):
        assert runner._alert_order(said), said
    for said in ("remember that my insurance renews on March 12", "recuerda que Anna está de vacaciones"):
        assert not runner._alert_order(said), said
