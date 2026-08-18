"""voice/engine/llm/providers/vault_intercept.py — regression coverage for the split-out vault/secrets
intercept (V2-108 cont., 2026-08-17 modularization pass). Extracted from `nucleo.py::_run_inner` with no
existing unit coverage (only reachable before via the full LiveKit session); now independently testable.
"""
import asyncio

import pytest

from voice.engine.llm.providers.vault_intercept import try_vault_intercept


def _run(text, first_turn=False):
    events, sent = [], []

    def emit(*a, **k):
        events.append((a, k))

    def send(txt):
        sent.append(txt)

    # V2-141: the intercept now answers «did I consume the turn?» AND «with what text does the turn go on?» —
    # the second half is what lets a request carrying a secret still get answered (see vault_carrier.py).
    handled, out_text = asyncio.run(try_vault_intercept(text, first_turn, send, emit))
    return handled, sent, events, out_text


def test_plain_chat_is_not_intercepted():
    handled, sent, events, _out = _run("hola, que tal el dia")
    assert handled is False
    assert not sent and not events


def test_first_turn_never_intercepted(monkeypatch):
    # even a security-config phrase must NOT short-circuit the kickoff turn.
    from nucleo.flash import vault_rules
    monkeypatch.setattr(vault_rules, "detect", lambda text: ("secrets_voice", False))
    handled, sent, events, _out = _run("no me digas los secretos por voz", first_turn=True)
    assert handled is False
    assert not sent and not events


def test_security_config_command_is_applied_and_spoken(monkeypatch):
    from nucleo.flash import vault_rules
    monkeypatch.setattr(vault_rules, "detect", lambda text: ("secrets_voice", False))
    monkeypatch.setattr(vault_rules, "apply", lambda cmd: "Vale, no te los diré por voz.")
    handled, sent, events, _out = _run("no me digas los secretos por voz")
    assert handled is True
    assert sent == ["Vale, no te los diré por voz."]
    assert events and events[0][0][:2] == ("secret", "config")


def test_spoken_secret_without_vault_asks_to_create_one(monkeypatch):
    from memory import secrets as memsecrets
    from memory import vault

    class _D:
        label, value, slot, sensitivity = "contraseña de Netflix", "hunter2", "secret:netflix:password", "high"

    monkeypatch.setattr(memsecrets, "detect", lambda text: [_D()])
    monkeypatch.setattr(vault, "exists", lambda: False)
    handled, sent, events, _out = _run("mi contraseña de Netflix es hunter2")
    assert handled is True
    assert len(sent) == 1 and any(w in sent[0].lower() for w in ("bóveda", "secreto", "vault", "secret"))
    assert events and events[0][0][:2] == ("secret", "no_vault")


def test_spoken_secret_with_vault_is_stored_and_confirmed(monkeypatch):
    from memory import secrets as memsecrets
    from memory import vault

    class _D:
        label, value, slot, sensitivity = "contraseña de Netflix", "hunter2", "secret:netflix:password", "high"

    stored = []

    monkeypatch.setattr(memsecrets, "detect", lambda text: [_D()])
    monkeypatch.setattr(vault, "exists", lambda: True)

    def _store_secret(label, value, *, slot=None, sensitivity="high"):
        stored.append((label, value, slot, sensitivity))

    monkeypatch.setattr(vault, "store_secret", _store_secret)

    async def _run_sync(fn, *a, **k):
        return fn(*a, **k)

    monkeypatch.setattr(asyncio, "to_thread", _run_sync)

    handled, sent, events, _out = _run("mi contraseña de Netflix es hunter2")
    assert handled is True
    assert stored == [("contraseña de Netflix", "hunter2", "secret:netflix:password", "high")]
    assert len(sent) == 1
    assert events and events[0][0][:2] == ("secret", "saved")


def test_a_broken_vault_rules_module_fails_open_to_no_intercept(monkeypatch):
    from nucleo.flash import vault_rules

    def _boom(text):
        raise RuntimeError("boom")

    monkeypatch.setattr(vault_rules, "detect", _boom)
    handled, sent, events, _out = _run("cualquier cosa")
    assert handled is False
    assert not sent and not events
