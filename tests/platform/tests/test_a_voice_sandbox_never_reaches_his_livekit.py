"""A voice sandbox talks to its OWN LiveKit server (refactor2710-01 T-07).

On the operator's LiveKit dev server a sandbox worker would be a second worker for automatic dispatch, so his real
sessions could land on the throwaway engine. The sandbox env must point the engine at a loopback server of its own
and carry no engine id; the LiveKit config must bind loopback only.

Disarm: point `voice_env` at 7880 or drop the `LIVEKIT_URL` it sets → red.
"""
from __future__ import annotations

import pytest

from tests.platform import voice_sandbox as vs
from tests.platform.sandbox_engine import free_port


def test_the_engine_points_at_the_sandbox_livekit_not_his():
    port = free_port()
    env = vs.voice_env(port)
    assert env["LIVEKIT_URL"] == f"ws://127.0.0.1:{port}"
    assert env["ZAELAR_ENGINE"] == "livekit"
    assert not env["ZAELAR_USER_ID"] and not env["FLY_MACHINE_ID"], "an engine id makes the sandbox read as hosted"
    with pytest.raises(ValueError):
        vs.voice_env(vs.OPERATOR_LIVEKIT_PORT)


def test_the_sandbox_livekit_binds_loopback_on_its_own_ports():
    cfg = vs.livekit_config(41001, 41002, 41003)
    assert "port: 41001" in cfg and "tcp_port: 41002" in cfg and "udp_port: 41003" in cfg
    assert '127.0.0.1' in cfg and "7880" not in cfg and "use_external_ip: false" in cfg
