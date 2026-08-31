"""The disposable engine's isolation contract, and ensuring nobody bypasses it by starting their own.

Written on 2026-08-20, when unifying `journey`'s startup with `use_cases`'. Until then, `journey`
started its own engine —its port, tempdir, and variable list—and that copy was missing
`ZAELAR_LOG_DIR`. The `LOG_DIR` in `voice/observer.py` is resolved from the REPO ROOT, not from the
workspace, so **every `journey` run wrote its events to the operator's real
`.meshkore/logs/timeline-latest.jsonl`**: test events read as a live session, which
is the incident from 2026-07-25.

And the warning was already written: `sandbox_engine.py` had contained a note about this exact leak for
months, because the helper was extracted from `journey`'s runner. Documenting a leak in the module that does
NOT have it does not fix it.

These tests do not start any engine: they intercept `Popen` and inspect the ENVIRONMENT passed to it, which is
where the contract lives. A test that actually started the engine would take a minute and test less.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests.platform import sandbox_engine as SE


class _FakeProc:
    returncode = None

    def poll(self):
        return None

    def terminate(self):
        pass

    def wait(self, *a, **k):
        pass

    def kill(self):
        pass


@pytest.fixture
def captured_env(monkeypatch):
    """Starts `sandbox_engine` without starting anything: returns the env with which the engine would have been launched."""
    seen: dict = {}

    def _popen(argv, **kw):
        seen["argv"] = argv
        seen["env"] = kw.get("env") or {}
        seen["cwd"] = kw.get("cwd")
        return _FakeProc()

    monkeypatch.setattr(SE.subprocess, "Popen", _popen)
    monkeypatch.setattr(SE, "_wait_ready", lambda eng, timeout: None)
    return seen


def test_the_operators_real_timeline_is_never_the_destination(captured_env):
    """The specific leak: without `ZAELAR_LOG_DIR`, test events end up in the operator's timeline."""
    with SE.sandbox_engine() as eng:
        env = captured_env["env"]
        assert env.get("ZAELAR_LOG_DIR"), "sin esta variable el observer escribe en la raíz del repo"
        assert Path(env["ZAELAR_LOG_DIR"]).is_relative_to(eng.workspace), (
            "el directorio de eventos tiene que caer DENTRO del workspace desechable")


def test_workspace_db_and_identity_are_all_isolated(captured_env):
    """`ZAELAR_WORKSPACE` takes `config/identity.json` with it, that is, the installation's `user_id`: without
    isolating it, a test run appears as another account in the Master's history."""
    with SE.sandbox_engine() as eng:
        env = captured_env["env"]
        for var in ("ZAELAR_WORKSPACE", "ZAELAR_DB", "ZAELAR_LOG_DIR"):
            assert Path(env[var]).is_relative_to(eng.workspace), f"{var} apunta fuera del workspace"


def test_the_noisy_neighbours_are_all_off(captured_env):
    """A disposable engine does not call the operator's real clusters, the LiveKit worker does not reappear, and it does not
    compete for the second TLS listener. Each of these once cost a run."""
    with SE.sandbox_engine():
        env = captured_env["env"]
        assert env["ZAELAR_ENGINE"] != "livekit", "el worker embebido de LiveKit no va en un desechable"
        assert env["MESHKORE_AUTORECONNECT"] == "0", "nunca marcar los clusters reales del operador"
        assert env["WA_ENABLED"] == "0" and env["TG_ENABLED"] == "0"
        assert env["ZAELAR_HOMEOSTASIS"] == "0"
        assert env["BRAIN"] == "nucleo", "el canal probe y los workers montan sobre este cerebro"


def test_credentials_are_deliberately_NOT_isolated(captured_env):
    """The opposite of an oversight: the goal is a clean BASE, not a crippled engine that cannot call a
    model. `server/common.py` deliberately loads `.env` + `.meshkore/credentials/` from the root."""
    with SE.sandbox_engine():
        env = captured_env["env"]
        assert "ZAELAR_CREDENTIALS_DIR" not in env
        assert env["HOST"] == "127.0.0.1", "y solo loopback: nada de escuchar en la red"


def test_a_caller_owned_log_path_survives_the_workspace(captured_env, tmp_path):
    """The log is the EVIDENCE of a broken startup, so whoever needs it after teardown can request
    its location. `journey` passes its run's `artifacts/` through this."""
    mine = tmp_path / "artifacts" / "journey-engine.log"
    with SE.sandbox_engine(log_path=mine) as eng:
        assert eng.log_path == mine
        assert mine.parent.is_dir(), "el directorio se crea, no se espera que exista"


def test_journey_boots_through_the_shared_helper_and_not_its_own(monkeypatch):
    """The other half, and the one that actually closes the leak: making `journey` USE the helper.

    It asserts behavior —was `sandbox_engine` called?— rather than reading the source: a test that
    searches for text in the code also finds what it is looking for inside the comment explaining the change.
    """
    from tests.journey import runner as R

    called: list[bool] = []

    class _Ctx:
        def __enter__(self):
            called.append(True)
            raise RuntimeError("corta aquí: solo se comprueba QUIÉN arranca el motor")

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(R, "sandbox_engine", lambda **kw: _Ctx())
    with pytest.raises(RuntimeError):
        R.run(0)
    assert called, "journey volvió a levantar su propio motor: la fuga de `ZAELAR_LOG_DIR` vuelve con él"
