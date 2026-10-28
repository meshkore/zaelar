"""V2-778 F0-6 — the torrent client is OFF in a hosted account unless the deployment turns it on.

The client shipped enabled by default everywhere, including a hosted account (`ZAELAR_USER_ID` set,
`nucleo/energy/account.is_cloud_account()`), where the machine that seeds is not the operator's own. The mechanism:
`service.enabled()` answers False there, whatever the operator switch says, unless `ZAELAR_TORRENT_IN_CLOUD=1`;
self-host is unchanged. The Files card hides its 🧲 door when the client is not available.
"""
from __future__ import annotations


from connectors.torrent import service



def test_self_host_keeps_the_operator_switch(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("ZAELAR_TORRENT_IN_CLOUD", raising=False)
    assert service.enabled() is True


def test_a_hosted_account_has_the_client_off(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "u-test")
    monkeypatch.delenv("ZAELAR_TORRENT_IN_CLOUD", raising=False)
    assert service.enabled() is False
    assert service.available() is False
    assert service.search_and_play("anything")["ok"] is False


def test_the_deployment_can_turn_it_on(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "u-test")
    monkeypatch.setenv("ZAELAR_TORRENT_IN_CLOUD", "1")
    assert service.enabled() is True
