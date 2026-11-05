"""Every exit a worker reaches is gated, or says in the code why it is open (V2-851 F2, §15c).

F0 found three ungated: `mesh serve` sent the errand text to a third-party agent with no consent and no outbound
scan; `/api/navegador/act` checked no token; `/api/agent/report` fails open on purpose. Now `mesh serve` crosses the
worker's exit gate (scan → consent class → taint) before the text leaves, the tab a worker drives answers only to its
token, the goal a report declares (what the task is judged against) needs the owner's token, and a browser submit
that leaves reads the session's taint.
"""
from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace

import pytest

from nucleo import untrusted
from nucleo.workers import taint


@pytest.fixture
def door(monkeypatch):
    from nucleo.cli import worker_api
    untrusted.reset()
    rec = SimpleNamespace(task_id="m1", uid="", started=time.time(), depth=0, trace_id="", surface="", sheet="",
                          native_sid="", waiting_on="", ask="", ask_corr="", parked=False, mandate={})
    monkeypatch.setattr(worker_api, "_verify", lambda *_a: rec)
    monkeypatch.setattr(worker_api, "_piggyback", lambda *_a: [])
    yield SimpleNamespace(api=worker_api, rec=rec)
    untrusted.reset()


def _serve(d, prompt):
    out = asyncio.run(d.api.worker_act(task_id="m1", token="t", action="mesh_serve",
                                       payload={"errand": "hotel in Rome", "prompt": prompt, "agent": "stayfinder"}))
    return json.loads(out.body)


def test_a_secret_in_the_errand_text_never_leaves(door):
    pem = "-----BEGIN " + "RSA " + "PRIVATE KEY-----"      # assembled here: the public-repo gate scans the source
    got = _serve(door, f"hotel in Rome, pay with key {pem} abc")
    assert not got["ok"] and "nothing was sent" in got["error"]


def test_after_reading_a_stranger_the_errand_text_is_asked(door):
    taint.mark(door.rec, "web")
    got = _serve(door, "hotel in Rome 2026-12-01 to 2026-12-03 for 2")
    assert got.get("status") == "pending" and "stayfinder" in door.api._ACTS[got["corr_id"]]["question"]


def test_a_clean_session_is_cleared_and_the_answer_it_will_read_taints_it(door):
    got = _serve(door, "hotel in Rome 2026-12-01 to 2026-12-03 for 2")
    assert got["ok"] and got["result"]["prompt"].startswith("hotel in Rome")
    assert taint.tainted(door.rec)


def test_the_bridge_sends_nothing_until_the_gate_clears_it(monkeypatch, capsys):
    from nucleo import mesh_agents
    from nucleo.cli import mesh as mesh_cli
    monkeypatch.setenv("ZAELAR_TASK_ID", "m1")
    monkeypatch.setattr(mesh_cli, "_leave_gate", lambda *_a: {"ok": True, "status": "pending", "corr_id": "c1"})
    monkeypatch.setattr(mesh_agents, "serve", lambda *a, **k: pytest.fail("the errand text left before his yes"))
    mesh_cli.main(["serve", "hotel in Rome"])
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "pending" and "c1" in out["reason"]


def test_a_tab_a_worker_drives_answers_only_to_its_token(monkeypatch):
    from nucleo import dispatch
    from widgets.navegador import act_api
    from widgets.navegador.act_api import entry
    rec = SimpleNamespace(task_id="w9", uid="")
    ran = []

    async def _run(task_id, action, args):
        ran.append(action)
        return {"ok": True}
    monkeypatch.setattr(entry, "_run_act", _run)
    monkeypatch.setattr(dispatch, "rec_token", lambda _r: "tok")
    monkeypatch.setattr(dispatch, "record_by_nav_task", lambda _t: rec)
    bad = asyncio.run(act_api.navegador_act(task_id="nav9", action="snapshot", args={}, token=""))
    assert bad.status_code == 403 and ran == []
    assert asyncio.run(act_api.navegador_act(task_id="nav9", action="snapshot", args={}, token="tok"))["ok"]
    monkeypatch.setattr(dispatch, "record_by_nav_task", lambda _t: None)
    monkeypatch.setattr(dispatch, "get_record", lambda _t: None)
    assert asyncio.run(act_api.navegador_act(task_id="free", action="snapshot", args={}))["ok"]   # no worker drives it


def test_the_goal_a_report_declares_needs_the_owners_token(monkeypatch):
    from nucleo import agent_api, dispatch
    from nucleo.circuit import spec
    goals = []
    monkeypatch.setattr(dispatch, "get_record", lambda _t: SimpleNamespace(task_id="r1"))
    monkeypatch.setattr(dispatch, "rec_token", lambda _r: "tok")
    monkeypatch.setattr(spec, "session_goal", lambda tid, dw: goals.append(tid))
    for name in ("session_reported", "session_phase"):
        monkeypatch.setattr(dispatch, name, lambda *a, **k: None, raising=False)
    dw = {"widget": "results", "expect": "present"}
    bare = dict(phase="", note="", plan="", progress=None, done=None, pct=None, considered=None, kept=None)
    asyncio.run(agent_api.agent_report(tid="r1", token="", done_when=dw, **bare))
    assert goals == []
    asyncio.run(agent_api.agent_report(tid="r1", token="tok", done_when=dw, **bare))
    assert goals == ["r1"]


def test_a_submit_that_leaves_after_reading_pages_is_asked(monkeypatch):
    from nucleo import dispatch
    from widgets.navegador import click_gate
    rec = SimpleNamespace(task_id="b1", uid="", mandate={})
    monkeypatch.setattr(dispatch, "record_by_nav_task", lambda _t: rec)
    sig = {"isSubmit": True, "pageUrl": "https://www.casalucio.es/reservas"}
    assert click_gate._tainted_submit("nav-b1", sig) == ""
    taint.mark(rec, "browser")
    assert "casalucio" in click_gate._tainted_submit("nav-b1", sig)
    rec.mandate = {"may": ["browser"]}
    assert click_gate._tainted_submit("nav-b1", sig) == ""
