"""The WhatsApp bridge is a sidecar: reused when it already answers, owned by `stop`, kept by `restart`.

Measured 2026-09-15. A `node bridge.js --port 3111` from 00:21 (PPID 1) had outlived every `make stop` of
the day — `scripts/zaelar.py` freed 43917/44317/45817/7880 and never named the bridge's port — so every
restart spawned a SECOND bridge that died with `EADDRINUSE`, while `wait_connected` went green because the
orphan answered `/health`. WhatsApp worked through a process no restart controlled: the same class the
Makefile already paid for with «media instancia sobrevivía a cada parada».

Two halves, one property each: `bridge_proc.start` asks the port before it spawns, and the launcher's
port table names the bridge — kept warm across a `restart` (it holds the paired session; re-pairing is a
QR the operator has to scan) and ended by a full `stop`.
"""
from __future__ import annotations

import asyncio
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


class _Spawned(Exception):
    pass


@pytest.fixture
def no_spawn(monkeypatch):
    """A spawn is the thing under test: make it loud, and make `node` look present so the check is reached."""
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/node")

    async def _boom(*a, **k):
        raise _Spawned(a[:2])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _boom)


def test_a_bridge_that_already_answers_is_REUSED(monkeypatch, no_spawn):
    from connectors.whatsapp import bridge_proc, client

    async def _health():
        return {"status": "connected"}
    monkeypatch.setattr(client, "health", _health)
    b = bridge_proc._Bridge()
    asyncio.run(b.start())                     # no _Spawned → nothing was launched
    assert b.proc is None, "a reused bridge is not our child; stop() must not try to kill it"


def test_a_bridge_that_is_up_but_not_yet_paired_is_STILL_the_bridge(monkeypatch, no_spawn):
    from connectors.whatsapp import bridge_proc, client

    async def _health():
        return {"status": "qr"}
    monkeypatch.setattr(client, "health", _health)
    asyncio.run(bridge_proc._Bridge().start())


def test_nothing_on_the_port_means_SPAWN(monkeypatch, no_spawn):
    from connectors.whatsapp import bridge_proc, client

    async def _health():
        raise ConnectionError("refused")
    monkeypatch.setattr(client, "health", _health)
    with pytest.raises(_Spawned) as e:
        asyncio.run(bridge_proc._Bridge().start())
    assert e.value.args[0][0] == "node"


def test_a_stranger_on_the_port_is_not_mistaken_for_the_bridge(monkeypatch, no_spawn):
    """`/health` answering is not enough: it must answer in the bridge's own shape."""
    from connectors.whatsapp import bridge_proc, client

    async def _health():
        return "ok"
    monkeypatch.setattr(client, "health", _health)
    with pytest.raises(_Spawned):
        asyncio.run(bridge_proc._Bridge().start())


# ── the launcher owns the port, and keeps it on a restart ────────────────────────────────────────────────

def _zaelar_py() -> str:
    return (ENGINE / "scripts" / "zaelar.py").read_text(encoding="utf-8")


def test_stop_owns_the_bridge_port():
    """`scripts/zaelar.py` is stdlib-only (a Windows user with no venv must be able to stop their instance),
    so the default is a literal there and must agree with `connectors/whatsapp/config.py`."""
    src = _zaelar_py()
    from connectors.whatsapp import config
    assert config.bridge_port() == 3111 or "WA_BRIDGE_PORT" in src
    table = src[src.index("PORTS = ["):src.index("]", src.index("PORTS = ["))]
    assert 'WA_BRIDGE_PORT", "3111"' in table, "the bridge port must be in the table `stop` walks"


def test_restart_keeps_the_bridge_and_stop_ends_it():
    src = _zaelar_py()
    assert "KEPT_ON_RESTART" in src
    kept = src[src.index("KEPT_ON_RESTART = {"):src.index("}", src.index("KEPT_ON_RESTART = {"))]
    assert "7880" in kept and "WA_BRIDGE_PORT" in kept, "livekit and the bridge both hold a session worth keeping"
    body = src[src.index("def cmd_stop("):src.index("def _venv_python(")]
    assert "port in KEPT_ON_RESTART" in body, "the keep decision reads the set, not a hardcoded livekit port"
