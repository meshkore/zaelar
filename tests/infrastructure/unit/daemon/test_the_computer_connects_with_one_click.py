"""«Conecta tu ordenador» without a terminal and without typing a path.

The screen used to send a person to a terminal (`./zaelar restart`, `make daemon`) and make them paste a folder's
full path. Now «Conectar» asks the engine to start the daemon it carries, and «Elegir carpeta…» asks the daemon
to open the system's own folder dialog — the chosen folder still goes through `roots.grant`, so the dialog is a
way IN, never a way AROUND the permission circuit.
"""
from __future__ import annotations

import subprocess

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from daemon import picker
from server import daemon_api

SAME = {"Sec-Fetch-Site": "same-origin"}


def _app(tmp_path, monkeypatch, *, cloud=False):
    monkeypatch.setattr(daemon_api, "_state_dir", lambda: tmp_path / "config" / "daemon")
    monkeypatch.setattr(daemon_api, "_is_cloud", lambda: cloud)
    monkeypatch.setattr(daemon_api, "_last_start", [0.0])
    app = FastAPI()
    app.include_router(daemon_api.router)
    return TestClient(app)


def test_connect_starts_the_daemon_this_engine_carries(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append((cmd, kw)))
    r = _app(tmp_path, monkeypatch).post("/api/daemon/start", headers=SAME)
    assert r.json() == {"ok": True, "started": True}
    cmd, kw = spawned[0]
    assert cmd[1:] == ["-m", "daemon"] and kw.get("cwd")


def test_a_second_click_does_not_start_a_second_daemon(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd))
    c = _app(tmp_path, monkeypatch)
    c.post("/api/daemon/start", headers=SAME)
    assert c.post("/api/daemon/start", headers=SAME).json().get("starting") and len(spawned) == 1


def test_the_cloud_and_another_site_cannot_start_it(tmp_path, monkeypatch):
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd))
    assert _app(tmp_path, monkeypatch, cloud=True).post("/api/daemon/start", headers=SAME).status_code == 409
    assert _app(tmp_path, monkeypatch).post("/api/daemon/start",
                                            headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not spawned


# ── the daemon side ────────────────────────────────────────────────────────────────────────────────────────

def test_a_prompt_cannot_close_the_dialog_script():
    p = picker._clean('Choose"); do shell script "rm -rf ~" --\\n$(x)`y`')
    assert not any(ch in p for ch in "\"'\\`$\n")


@pytest.mark.parametrize("returncode,out,expected", [(0, "/Users/x/Docs/\n", "/Users/x/Docs"), (1, "", "")])
def test_a_cancel_is_nothing_and_a_choice_is_its_path(monkeypatch, returncode, out, expected):
    monkeypatch.setattr(picker, "_command", lambda prompt: ["dialog"])
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, returncode, stdout=out, stderr=""))
    assert picker.choose_folder("x") == expected


def test_the_picked_folder_goes_through_the_same_boundary(monkeypatch):
    from daemon.fs import refusal, roots
    from daemon.http import routes
    monkeypatch.setattr(picker, "choose_folder", lambda prompt="": "/Users/x/.ssh")

    def _refuse(path):
        raise refusal.Refusal("sensitive", "that folder holds credentials")
    monkeypatch.setattr(roots, "grant", _refuse)
    with pytest.raises(refusal.Refusal):
        routes.pick(type("R", (), {"_caller": lambda self: "test"})(), {"prompt": "x"})
    monkeypatch.setattr(picker, "choose_folder", lambda prompt="": "")
    monkeypatch.setattr(roots, "roots", lambda: [])
    assert routes.pick(type("R", (), {"_caller": lambda self: "test"})(), {})["cancelled"] is True


def test_a_cloud_account_is_recognised_without_a_stub(monkeypatch):
    """`_is_cloud` once imported a module that does not exist and so always answered «local». Every other test here
    stubs `_is_cloud`; this one does not."""
    monkeypatch.setenv("ZAELAR_USER_ID", "00000000-0000-4000-8000-000000000001")
    assert daemon_api._is_cloud() is True
    monkeypatch.delenv("ZAELAR_USER_ID")
    assert daemon_api._is_cloud() is False
