"""Telegram connects like WhatsApp when the install ships Zaelar's own app (2026-10-04).

Telegram's user API needs an app identity (api_id/api_hash). Asking every operator to register one at
my.telegram.org was the hard step; the install now carries Zaelar's own app in its credentials env
(TG_API_ID/TG_API_HASH, never the repo), so connecting is the QR alone. His own app still wins when typed.
"""
from __future__ import annotations



def test_an_empty_connect_is_valid_when_the_install_has_the_app(monkeypatch):
    from connectors.messaging import control
    monkeypatch.setenv("TG_API_ID", "12345678")
    monkeypatch.setenv("TG_API_HASH", "0" * 32)
    assert control.validate_connect("telegram", {}) is None


def test_without_the_app_the_two_values_are_still_asked(monkeypatch):
    from connectors.messaging import control
    monkeypatch.delenv("TG_API_ID", raising=False)
    monkeypatch.delenv("TG_API_HASH", raising=False)
    assert control.validate_connect("telegram", {}), "with no app anywhere, the form has to ask"


def test_a_half_typed_own_app_is_refused_even_with_the_install_app(monkeypatch):
    from connectors.messaging import control
    monkeypatch.setenv("TG_API_ID", "12345678")
    monkeypatch.setenv("TG_API_HASH", "0" * 32)
    assert control.validate_connect("telegram", {"api_id": "abc", "api_hash": ""})


def test_the_tab_learns_the_app_is_shipped(monkeypatch):
    from connectors import registry
    monkeypatch.setenv("TG_API_ID", "12345678")
    monkeypatch.setenv("TG_API_HASH", "0" * 32)
    row = next(r for r in registry.descriptors() if r["id"] == "telegram")
    assert row["config"].get("app_shipped") is True
    assert "api_hash" not in row["config"], "the hash never reaches the browser"
