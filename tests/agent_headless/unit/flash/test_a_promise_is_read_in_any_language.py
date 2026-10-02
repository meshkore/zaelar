"""Whether the reply PROMISED something is read by a verdict, in any language (V2-778 F2-16, 2026-10-02).

«Did the reply promise an act / music it did not deliver?» opens the promise backstops and the act repair, and it
was answered by phrase tables in two languages (`router_guards._PROMISE_RE`, `promise._PROMISE_EN_RE`,
`playback_promise`) — blind in French, German, Italian, Catalan…, and the doctrine's own example of a verb table
pretending to be a router (V2-750). The operator's decision: ask the verdict on EVERY spoken reply. One Jev question
per turn, asked once off the voice loop when the reply is final; the tables stay as the PROPOSAL used when the verdict
cannot answer (Jev down, unsure).
"""
from __future__ import annotations

import pytest

from nucleo.flash import reply_promise as RP
from nucleo.flash import router as RG          # the names every caller imports: verdict first, tables behind
from nucleo.flash import playback_promise as PB


@pytest.fixture(autouse=True)
def _clean():
    RP.reset()
    yield
    RP.reset()


def _verdict(monkeypatch, choice, confidence=0.95):
    """Jev answering through its non-blocking door: a ready handle, and `read` keeping its own confidence gate."""
    import threading

    from nucleo import jev
    ev = threading.Event()
    ev.set()
    monkeypatch.setattr(jev, "ask_many", lambda *a, **k: {"event": ev})
    monkeypatch.setattr(jev, "read", lambda h, key, fb, **k: (choice, {"used": True}) if confidence >= jev.MIN_CONFIDENCE
                        else (fb, {"used": False}))


def test_a_french_promise_the_tables_cannot_read_is_read(monkeypatch):
    reply = "Je l'envoie à Quinn tout de suite."
    assert not RG.promises_action(reply), "precondition: the tables are blind to French"
    _verdict(monkeypatch, "act")
    RP.read_now(reply, "envoie-le à Quinn")
    assert RG.promises_action(reply)


def test_the_verdict_vetoes_a_table_false_positive(monkeypatch):
    reply = "I'll be honest: it's sunny all week in Soria."
    _verdict(monkeypatch, "none")
    RP.read_now(reply, "what's the weather like")
    assert not RG.promises_action(reply)


def test_a_music_promise_in_german_opens_the_music_backstop(monkeypatch):
    reply = "Klar, ich lege jetzt Like a Prayer auf."
    _verdict(monkeypatch, "music")
    RP.read_now(reply, "leg Like a Prayer auf")
    assert RG.promises_music(reply) and PB.promises_playback(reply, "leg Like a Prayer auf")
    assert RG.promises_action(reply), "a promise to play is a promise to act"


def test_an_unsure_or_absent_verdict_leaves_the_tables_to_decide(monkeypatch):
    reply = "Voy a mandárselo a Quinn ahora mismo."
    _verdict(monkeypatch, "none", confidence=0.2)        # a shrug
    RP.read_now(reply, "mándaselo a Quinn")
    assert RG.promises_action(reply) is True, "an unsure verdict must not veto the proposal"
    RP.reset()
    from nucleo import jev
    monkeypatch.setattr(jev, "ask_many", lambda *a, **k: None)        # Jev down / disabled
    RP.read_now(reply, "mándaselo a Quinn")
    assert RG.promises_action(reply) is True


def test_both_channels_ask_once_when_the_reply_is_final():
    from pathlib import Path
    root = Path(__file__).resolve().parents[4]
    for rel in ("nucleo/flash/post_stream.py", "nucleo/flash/probe_mirrors.py"):
        src = (root / rel).read_text("utf-8")
        assert "reply_promise.prefetch(" in src, f"{rel} does not ask the verdict"
