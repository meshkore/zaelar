"""An answer to a confirmation that does not exist is no act, and the turn says so (refactor2710-99, bank class A).

Bank `msg-es-send-draft` («Envíalo», 7 → 4): in three reds the model called `confirm_widget_delete` — the answer to
a pending confirmation — when nothing was pending, and said «Hecho.». The confirm door resolved nothing, in silence,
so the false «done» stood and nothing was sent.

Now the door reads the pending set first: with nothing waiting for a yes, the call resolves nothing, the turn's
line is the truth in the agent's language («there was nothing waiting for a yes…»), and the timeline says why. A
real pending confirmation is answered exactly as before.
"""
from __future__ import annotations

import pytest

from nucleo.flash import tool_executor_calls as _calls


def _confirm(said: str, *, pending: dict, monkeypatch) -> tuple[bool, dict, list, list]:
    from widgets import confirm as wc
    monkeypatch.setattr(wc, "pending", lambda: pending)
    monkeypatch.setattr(wc, "backs_a_yes", lambda s: True)
    resolved: list = []
    events: list = []
    clarify: dict = {"msg": ""}
    out = _calls._t_confirm({"confirmed": True}, said, lambda ok: resolved.append(ok) or True, clarify,
                            lambda *a, **k: events.append((a, k)))
    return out, clarify, resolved, events


@pytest.mark.parametrize("code,said", [("es", "Envíalo"), ("en", "Send it")])
def test_a_yes_with_nothing_pending_resolves_nothing_and_says_so(code, said, monkeypatch):
    from i18n import langs
    monkeypatch.setattr(langs, "current_language", lambda: langs.LANGUAGES[code])
    out, clarify, resolved, events = _confirm(said, pending={}, monkeypatch=monkeypatch)
    assert out is False and resolved == [], "nothing was pending, so nothing may be resolved"
    assert clarify["msg"] == langs.LANGUAGES[code].confirm_nothing_pending and clarify["msg"], clarify
    assert any((k.get("extra") or {}).get("kind_diag") == "confirm_nothing_pending" for _a, k in events)


def test_a_real_pending_confirmation_is_answered_as_before(monkeypatch):
    out, clarify, resolved, _events = _confirm("Sí, bórrala", pending={"agenda": {"question": "¿La borro?"}},
                                               monkeypatch=monkeypatch)
    assert out is True and resolved == [True] and not clarify["msg"]


def test_both_languages_carry_the_line():
    from i18n import langs
    assert all(langs.LANGUAGES[c].confirm_nothing_pending for c in ("es", "en"))
