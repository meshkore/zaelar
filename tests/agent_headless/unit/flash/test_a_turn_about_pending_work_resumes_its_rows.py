"""V2-799 — a turn about PENDING work resolves to the durable pending rows, and each one resumes FROM ITS ROW.

Live (2026-10-26): an email held for his «send it» and a table hunt waiting for his pick. «termina esas tareas»: the
model wrote two complete commissions; the fragment guard annulled both, a backstop glued an old utterance to the new
one («Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — termina esas tareas»), date/time/party/area were
lost, and the worker refused. The refusal then became the browser card's title.

Here: Spanish and English turns; an email + an errand pending together; one pending; none pending (and then the
verdict is never paid for); a live errand is not started twice; the card title is the errand's name.
"""
from __future__ import annotations

import asyncio
import pathlib
import time

import pytest

from nucleo import pending_work
from nucleo.flash import resume_turn

ROOT = pathlib.Path(__file__).resolve().parents[4]
GOAL = "Reserva mesa para 2 el lunes a las 14:00 en un restaurante del centro de Soria"


@pytest.fixture(autouse=True)
def _sandbox(tmp_path, monkeypatch):
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wstore, "_last_hash", {})
    resume_turn.reset()
    pending_work.forget_cache()
    from nucleo.circuit import ledger as tasks
    ts = tasks.store()
    ts.tasks_clear(states=ts.LIVE_STATES + ts.DONE_STATES, modes=("now",))
    yield
    ts.tasks_clear(states=ts.LIVE_STATES + ts.DONE_STATES, modes=("now",))
    resume_turn.reset()
    pending_work.forget_cache()


def _errand(uid="b00t01-1", state="done", goal=GOAL, outcome="La que mejor encaja: Garoa — ¿te la reservo?"):
    from nucleo.circuit import ledger as tasks
    now = int(time.time())
    tasks.store().task_put({"id": uid, "title": "Reservar mesa en Soria", "goal": goal, "kind": "web", "mode": "now",
                            "state": state, "visible": True, "origin": "voz", "created_at": now - 600,
                            "started_at": now - 600, "finished_at": now - 60 if state == "done" else None,
                            "outcome": outcome, "sheet": "results--3"})


def _held_email():
    from widgets.mensajeria import data
    data.apply_action("draft", {"contact": "hospitality@example.com", "subject": "API access", "text": "Hola"})


def _verdict(monkeypatch, wanted_sources, calls):
    from nucleo import jev

    def pick(rows, criteria, **_k):
        calls.append(criteria)
        return [{"candidate": r, "fit": "strong", "confidence": 0.95} for r in rows if r["source"] in wanted_sources]
    monkeypatch.setattr(jev, "select_many", pick)


def _escalations(monkeypatch):
    from nucleo.flash import escalate
    got = []
    monkeypatch.setattr(escalate, "escalate_to_slowbrain", lambda req, context=None: got.append((req, context)) or 1)
    return got


def _take(text, ops):
    req = {"v": "Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — " + text, "more": []}
    took = asyncio.run(resume_turn.take(req, operator_text=text, last_reply="Hecho.",
                                        apply_widget_data=lambda w, a, p: ops.append((w, a, p))))
    return took, req


@pytest.mark.parametrize("text", ["termina esas tareas", "finish those two things"])
def test_an_email_and_an_errand_pending_together_both_resume_from_their_rows(monkeypatch, text):
    _errand()
    _held_email()
    calls, ops = [], []
    _verdict(monkeypatch, {"task", "widget"}, calls)
    esc = _escalations(monkeypatch)
    took, req = _take(text, ops)
    assert took and req["v"] is None and req["more"] == [] and len(req["resumed"]) == 2
    # the email: through its OWN declared action (its own confirm gate), named by its recipient
    assert ops == [("mensajeria", "send_draft", {"contact": "hospitality@example.com"})]
    # the errand: its own brief verbatim, its row and its sheet — no glued utterance, no blind restart
    (brief, ctx), = esc
    assert brief.startswith(GOAL) and "Garoa" in brief and text in brief
    assert "Serías capaz" not in brief
    assert ctx["task_uid"] == "b00t01-1" and ctx["sheet"] == "results--3" and ctx["src"] == "resume"


def test_one_pending_row_is_one_resumption(monkeypatch):
    _errand()
    calls, ops = [], []
    _verdict(monkeypatch, {"task"}, calls)
    esc = _escalations(monkeypatch)
    took, req = _take("sigue con lo de antes", ops)
    assert took and len(esc) == 1 and ops == []


def test_nothing_pending_pays_no_verdict_and_keeps_todays_path(monkeypatch):
    calls, ops = [], []
    _verdict(monkeypatch, {"task", "widget"}, calls)
    took, req = _take("termina esas tareas", ops)
    assert not took and calls == [] and req["v"] is not None


def test_a_turn_that_means_no_pending_row_keeps_todays_path(monkeypatch):
    _errand()
    calls, ops = [], []
    _verdict(monkeypatch, set(), calls)
    took, req = _take("ponme música", ops)
    assert not took and len(calls) == 1 and req["v"] is not None


def test_a_live_errand_is_not_started_twice(monkeypatch):
    _errand(uid="b00t01-2", state="waiting")
    calls, ops = [], []
    _verdict(monkeypatch, {"task"}, calls)
    esc = _escalations(monkeypatch)
    took, req = _take("termina esa tarea", ops)
    assert took and esc == [] and req["resumed"] == ["b00t01-2"]


def test_both_doors_ask_the_rows_before_annulling_or_gluing():
    words = (ROOT / "nucleo/flash/post_stream_words.py").read_text(encoding="utf-8")
    assert words.index("_resume_turn.before_fragment_guard(") < words.index("_pst._eguard.drop_if_fragment(")
    lanes = (ROOT / "nucleo/flash/post_stream_lanes.py").read_text(encoding="utf-8")
    i = lanes.index("_no_tool = await _pst._resume_turn.before_backstops(")
    assert i < lanes.index('escalate_req["v"] = _win_goal or _op_text') and i < lanes.index("hands_public_lookup_back")


def test_a_resumed_turn_leaves_no_backstop_to_rebuild_a_brief(monkeypatch):
    """`before_backstops` returns the `_no_tool` both promise backstops read: once rows resumed, neither runs."""
    _errand()
    calls = []
    _verdict(monkeypatch, {"task"}, calls)
    _escalations(monkeypatch)
    from nucleo.turn import reply
    monkeypatch.setattr(reply, "owes_an_act", lambda b: "order" if b == "ORDER" else "")
    esc, acted = {"v": None, "more": []}, {}
    no_tool = asyncio.run(resume_turn.before_backstops(True, esc, spoken_text="Retomo lo del restaurante.",
                                                      operator_text="termina esas tareas", brief="ORDER", last_reply="",
                                                      apply_widget_data=None, emit=None, acted=acted))
    assert no_tool is False and esc["resumed"] == ["b00t01-1"]
    assert asyncio.run(resume_turn.before_backstops(True, {"v": None, "more": []}, spoken_text="", operator_text="x",
                                                    brief=None, last_reply="", apply_widget_data=None, emit=None,
                                                    acted={})) is True, "no act owed by the brief, nothing to complete"


# ── the card's title is the errand's NAME, never a summariser's or a worker's sentence ──────────────────

def test_the_card_title_is_the_errand_name_and_a_summary_never_overwrites_it():
    from widgets.navegador import data as navdata, tasks as navtasks
    tid = navtasks.create("Vale. ¿Serías capaz de reservarme, Johnny, un restaurante — termina esas tareas",
                          "Reservar restaurante")
    navtasks.set_goal_summary(tid, "No se puede: la petición no contiene objetivo, criterios, tipo")
    assert navdata._task_view(navtasks.get(tid))["title"] == "Reservar restaurante"
    navtasks.set_title(tid, "Mesa para 2 en Soria")
    assert navdata._task_view(navtasks.get(tid))["title"] == "Mesa para 2 en Soria"


def test_a_browser_card_is_born_with_the_errands_name_and_renamed_with_it():
    src = (ROOT / "nucleo/dispatch_prepare.py").read_text(encoding="utf-8")
    assert "navtasks.create(req, _errand_name(rec, req)" in src
    assert "_navtasks.set_title(rec.nav_task, t)" in src


# ── the MODEL resumes, from the state it is shown; the verdict only completes it ─────────────────────────

def test_the_prompt_carries_pending_rows_only_when_there_are_any():
    pending_work.forget_cache()
    assert pending_work.prompt_lines() == []
    _errand()
    _held_email()
    pending_work.forget_cache()
    lines = pending_work.prompt_lines()
    assert lines[0].startswith("PENDIENTE") and any("b00t01-1" in l and "Reservar mesa en Soria" in l for l in lines)
    assert any(l.startswith("· mensajeria:") for l in lines), "a row the mail card holds for his word is listed"
    from nucleo.flash import live_blocks
    assert "_live_blocks.pending_work_lines()" in (ROOT / "nucleo/flash/prompt.py").read_text(encoding="utf-8")
    assert live_blocks.pending_work_lines() == lines


def test_the_resume_tool_is_offered_only_when_something_is_pending():
    from nucleo.flash import router
    names = lambda ctx: [t["function"]["name"] for t in router.tools(ctx)]   # noqa: E731
    assert "resume_task" in names(router.tool_context(has_pending=True))
    assert "resume_task" not in names(router.tool_context(has_pending=False))


def test_the_tool_resumes_the_rows_the_model_named_and_drops_invented_ids(monkeypatch):
    _errand()
    _held_email()
    pending_work.forget_cache()
    rows = pending_work.by_ids(["b00t01-1", "nonexistent-9", "mensajeria:" + "to:email:hospitality@example.com"])
    assert [r["id"] for r in rows] == ["b00t01-1", "mensajeria:to:email:hospitality@example.com"]
    src = (ROOT / "nucleo/flash/tool_executor_calls.py").read_text(encoding="utf-8")
    assert "_resume_turn.from_tool(args" in src[src.index('elif name == "resume_task":'):][:300]
    esc, ops, acted = {"v": None, "more": []}, [], {}
    resume_turn.from_tool({"ids": ["nonexistent-9"]}, escalate_req=esc, operator_text="x",
                          apply_widget_data=lambda *a: ops.append(a), emit=None, acted=acted)
    assert "resumed" not in esc and ops == [], "an invented id resumes nothing"


def test_an_errand_the_energy_lease_stopped_is_resumable_days_later():
    from nucleo.circuit import ledger as tasks
    now = int(time.time())
    tasks.store().task_put({"id": "b00t01-7", "title": "Playlist de fiesta", "goal": "Haz una playlist de fiesta",
                            "kind": "code", "mode": "now", "state": "failed", "visible": True, "origin": "voz",
                            "created_at": now - 3 * 86400, "started_at": now - 3 * 86400,
                            "finished_at": now - 3 * 86400 + 60,
                            "outcome": 'API Error: 402 {"error":"out_of_energy"}'})
    pending_work.forget_cache()
    (row,) = [r for r in pending_work.rows() if r["id"] == "b00t01-7"]
    assert row["state"] == "stopped_by_energy"


# ── the harness: «confirmed» and «done» are checked separately ──────────────────────────────────────────

def test_a_confirmed_send_owes_its_end_state_and_a_send_that_did_not_happen_is_unmet():
    """A «yes» that leads to nothing must be impossible: the confirmed path (`dispatch_and_report(receipt=True)`)
    opens the action's declared end state, and `send_draft` now declares one — a sent row for that recipient."""
    from nucleo.circuit import spec
    from widgets.mensajeria import data
    _held_email()
    e = spec.open_for_action("mensajeria", "send_draft", {"contact": "hospitality@example.com"}, text="sí")
    assert e is not None, "the end state must render for a held send"
    assert spec.attest(e) is False, "nothing sent yet: unmet, never a silent «done»"
    data.apply_action("send_draft", {"contact": "hospitality@example.com"})
    assert spec.attest(e) is True
