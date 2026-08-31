#
# Scoped dev worker (V2-076, cluster escalation with code permission). Run: .venv/bin/pytest tests/agent_headless/unit/test_dev_worker.py -q
#
# The decision to set up a dev worker is a PURE helper (testable without spawning). The critical security points: it is
# activated only with `dev`+`repo`; its tools are Read/Write/Edit + the git BRIDGE (never bare Bash); no memory bridges;
# scoped repo. Without `dev` → None → normal worker (zero regression).
#
from nucleo import dispatch
from tests.agent_headless.unit.test_dispatch import fake_backend, fresh_db  # noqa: F401 — shared integration fixtures
                                                          # fake; never launches a real `claude`)


def test_no_dev_context_returns_none():
    assert dispatch._dev_worker_params(None) is None
    assert dispatch._dev_worker_params({"src": "cluster", "trusted": False}) is None   # without code permission
    assert dispatch._dev_worker_params({"dev": True}) is None                          # dev but without repo → None


def test_dev_context_scoped_params():
    p = dispatch._dev_worker_params({"dev": True, "repo": "meshkore/algo", "trusted": False})
    assert p is not None
    assert p["repo"] == "meshkore/algo"
    # git ONLY through the bridge, never bare Bash
    assert any("nucleo.git_cli" in t for t in p["tools"])
    assert not any(t == "Bash" or t.startswith("Bash(git") for t in p["tools"])
    # no memory bridges + scoped repo
    assert p["env"]["ZAELAR_NO_BRIDGE_TOOLS"] == "1"
    assert p["env"]["ZAELAR_ALLOWED_REPO"] == "meshkore/algo"
    assert "PYTHONPATH" in p["env"]                          # the bridge importable from the temporary cwd


def test_dev_prompt_scopes_to_repo_and_bridge():
    pr = dispatch._dev_prompt("haz el backtester", "meshkore/algo").lower()
    assert "meshkore/algo" in pr and "git_cli" in pr
    assert "temporal" in pr or "aislada" in pr              # makes the cwd isolation clear


# ── REAL confinement guard + cleanup (audit 2026-07-26 — closes "prompt convention only") ──────────
def test_dev_worker_wires_confinement_guard_and_cleans_up(fresh_db, fake_backend):
    """Integration with dispatch._run_session through the fake backend (never launches a real `claude`, INI-006-style)."""
    import asyncio
    import os

    task = dispatch.Task(id="dev1", request="arregla el backtester",
                         context={"dev": True, "repo": "meshkore/algo"}, trusted=False)
    asyncio.run(dispatch.dispatch(task))
    spec = fake_backend["last"].seen_spec
    assert spec.kind == "dev"
    # the hook reads ZAELAR_DEV_WORKER_ROOT == exactly the worker's isolated cwd (never the project)
    assert spec.env["ZAELAR_DEV_WORKER_ROOT"] == spec.cwd
    assert spec.extra_args[:1] == ["--settings"]
    settings_path = spec.extra_args[1]
    assert "zaelar-dev-settings-dev1" in settings_path
    # cwd + settings existed DURING the session (the fake backend saw them) — we cannot check them "live" with
    # an instantaneous fake backend, but dispatch DOES create them with the correct content and cleans them up at the end.
    assert not os.path.isdir(spec.cwd)          # T-07: cleaned up at the end of the session (previously: disk leak)
    assert not os.path.exists(settings_path)    # same for the guard's settings file


def test_dev_worker_settings_file_has_correct_hook_while_alive(fresh_db, monkeypatch):
    """Variant that INSPECTS the file before dispatch deletes it: a fake backend that does not return until
    the test releases it, to read the real settings.json while the session is alive."""
    import asyncio
    import json

    from nucleo.workers.base import WorkerBackend, WorkerEvent

    captured: dict = {}

    class _PausingBackend(WorkerBackend):
        name = "fake-pause"

        async def start(self, prompt, *, spec):
            captured["spec"] = spec
            with open(spec.extra_args[1], encoding="utf-8") as fh:
                captured["settings"] = json.load(fh)

        async def send(self, text):
            pass

        async def events(self):
            tid = captured["spec"].task_id
            yield WorkerEvent(task_id=tid, type="result", backend=self.name, data={"summary": "ok", "ok": True})
            yield WorkerEvent(task_id=tid, type="done", backend=self.name)

        async def stop(self, *, grace: float = 3.0):
            pass

        @property
        def alive(self):
            return False

    monkeypatch.setattr(dispatch, "get_backend", lambda spec: _PausingBackend())
    task = dispatch.Task(id="dev2", request="sube el fix", context={"dev": True, "repo": "meshkore/algo"},
                        trusted=False)
    asyncio.run(dispatch.dispatch(task))
    hook = captured["settings"]["hooks"]["PreToolUse"][0]
    assert "nucleo.dev_worker_guard" in hook["hooks"][0]["command"]
    assert "Read" in hook["matcher"] and "Write" in hook["matcher"]
