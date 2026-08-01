#
# Dev worker acotado (V2-076, escalada de cluster con permiso de código). Run: .venv/bin/pytest tests/agent_headless/unit/test_dev_worker.py -q
#
# La decisión de montar un dev worker es un helper PURO (testeable sin spawnear). Lo crítico de seguridad: solo se
# activa con `dev`+`repo`; sus tools son Read/Write/Edit + el PUENTE git (nunca Bash pelado); sin puentes de memoria;
# repo acotado. Sin `dev` → None → worker normal (cero regresión).
#
from nucleo import dispatch
from tests.agent_headless.unit.test_dispatch import fake_backend, fresh_db  # noqa: F401 — shared integration fixtures
                                                          # falso; nunca lanza un `claude` real)


def test_no_dev_context_returns_none():
    assert dispatch._dev_worker_params(None) is None
    assert dispatch._dev_worker_params({"src": "cluster", "trusted": False}) is None   # sin permiso de código
    assert dispatch._dev_worker_params({"dev": True}) is None                          # dev pero sin repo → None


def test_dev_context_scoped_params():
    p = dispatch._dev_worker_params({"dev": True, "repo": "meshkore/algo", "trusted": False})
    assert p is not None
    assert p["repo"] == "meshkore/algo"
    # git SOLO por el puente, nunca Bash pelado
    assert any("nucleo.git_cli" in t for t in p["tools"])
    assert not any(t == "Bash" or t.startswith("Bash(git") for t in p["tools"])
    # sin puentes de memoria + repo acotado
    assert p["env"]["ZAELAR_NO_BRIDGE_TOOLS"] == "1"
    assert p["env"]["ZAELAR_ALLOWED_REPO"] == "meshkore/algo"
    assert "PYTHONPATH" in p["env"]                          # el puente importable desde el cwd temporal


def test_dev_prompt_scopes_to_repo_and_bridge():
    pr = dispatch._dev_prompt("haz el backtester", "meshkore/algo").lower()
    assert "meshkore/algo" in pr and "git_cli" in pr
    assert "temporal" in pr or "aislada" in pr              # deja claro el aislamiento del cwd


# ── guard de confinamiento REAL + limpieza (auditoría 2026-07-26 — cierra "solo convención de prompt") ──────────
def test_dev_worker_wires_confinement_guard_and_cleans_up(fresh_db, fake_backend):
    """Integración con dispatch._run_session vía el backend falso (nunca lanza un `claude` real, INI-006-style)."""
    import asyncio
    import os

    task = dispatch.Task(id="dev1", request="arregla el backtester",
                         context={"dev": True, "repo": "meshkore/algo"}, trusted=False)
    asyncio.run(dispatch.dispatch(task))
    spec = fake_backend["last"].seen_spec
    assert spec.kind == "dev"
    # el hook lee ZAELAR_DEV_WORKER_ROOT == exactamente el cwd aislado del worker (nunca el proyecto)
    assert spec.env["ZAELAR_DEV_WORKER_ROOT"] == spec.cwd
    assert spec.extra_args[:1] == ["--settings"]
    settings_path = spec.extra_args[1]
    assert "zaelar-dev-settings-dev1" in settings_path
    # cwd + settings existían DURANTE la sesión (el backend falso los vio) — no podemos comprobarlos "en vivo" con
    # un backend falso instantáneo, pero SÍ que dispatch los crea con contenido correcto y los limpia al terminar.
    assert not os.path.isdir(spec.cwd)          # T-07: limpiado al acabar la sesión (antes: fuga de disco)
    assert not os.path.exists(settings_path)    # ídem para el fichero de settings del guard


def test_dev_worker_settings_file_has_correct_hook_while_alive(fresh_db, monkeypatch):
    """Variante que INSPECCIONA el fichero antes de que dispatch lo borre: un backend falso que no vuelve hasta
    que el test lo libera, para leer el settings.json real mientras la sesión está viva."""
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
