"""A sandbox never reaches the operator's messaging accounts — not his WhatsApp bridge, not his sessions.

Measured for `best-plumber-same-day__es` (2026-10-14), where a worker inside a use-case sandbox tried to WhatsApp
two real plumbers. That round could not send: `WA_ENABLED=0`/`TG_ENABLED=0` keep the connectors off, so nothing
consumed `msg.send`. But `ZAELAR_WORKSPACE` does not reach the connectors' OWN state: the WhatsApp and Telegram
sessions default to the repo's `connectors/*/_session/` — his paired accounts — and `bridge_proc.start` REUSES
any bridge already answering on `WA_BRIDGE_PORT` (3111 by default, the port his engine's bridge holds). Anything
that turned WhatsApp on inside a sandbox would have sent from his real number. The sandbox now owns those too.

Like `test_sandbox_isolation.py`, this starts no engine: it reads the environment `Popen` would receive.
"""
from __future__ import annotations

from pathlib import Path

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


def _env(monkeypatch) -> tuple[dict, Path]:
    seen: dict = {}

    def _popen(argv, **kw):
        seen["env"] = kw.get("env") or {}
        return _FakeProc()

    monkeypatch.setattr(SE.subprocess, "Popen", _popen)
    monkeypatch.setattr(SE, "_wait_ready", lambda eng, timeout: None)
    with SE.sandbox_engine() as eng:
        return seen["env"], eng.workspace


def test_the_messaging_sessions_live_in_the_throwaway_workspace(monkeypatch):
    env, ws = _env(monkeypatch)
    for var in ("WA_SESSION_DIR", "TG_SESSION_DIR"):
        assert env.get(var) and Path(env[var]).is_relative_to(ws), f"{var} points at his real session"


def test_the_whatsapp_bridge_port_is_not_his(monkeypatch):
    from connectors.whatsapp import config as wac
    env, _ = _env(monkeypatch)
    port = env.get("WA_BRIDGE_PORT")
    assert port and port.isdigit() and int(port) != 3111, "3111 is the operator's live bridge"
    monkeypatch.setenv("WA_BRIDGE_PORT", port)
    assert wac.bridge_port() == int(port), "the connector must read the sandbox's port"


def test_every_messaging_connector_is_off(monkeypatch):
    env, _ = _env(monkeypatch)
    assert env["WA_ENABLED"] == "0" and env["TG_ENABLED"] == "0" and env.get("EMAIL_ENABLED") == "0"
