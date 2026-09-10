"""V2-654 — the microphone state has ONE door, and a rule nobody has to remember.

Measured 2026-09-10 (session 85eec898): six files wrote `store.setMicMuted` + `localStorage`, and FOUR of
them never called `applyMic()` — the boot probe, the ⏻ power button on both shells, and the mobile dock. So
the 🎤 icon read CLOSED over a live track and the engine heard the operator for seven minutes.

The remedy is not "remember to call applyMic": a rule each caller has to remember is not a rule (the same
doctrine that closed the control-plane credential holes). `services/mic.js` is the door, and this file is
what stops the next writer from walking around it.
"""
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[4] / "frontend"
DOOR = FRONTEND / "app/services/mic.js"
STORE = FRONTEND / "app/core/store.js"


def _sources():
    """Every frontend module except the vendored SDK — a vendored library is not ours to route."""
    for p in sorted(FRONTEND.rglob("*.js")):
        if "vendor" in p.parts:
            continue
        yield p


def _stripped(p: Path) -> str:
    """Comments explain the OLD behaviour by quoting it — the V2-573 lesson, paid by a regex that matched
    the sentence describing a call instead of the call."""
    src = p.read_text(encoding="utf-8")
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)//.*$", "", src)


# ── the door itself ──────────────────────────────────────────────────────────────────────────────────────

def test_the_door_moves_all_four_things_at_once():
    """Signal, storage, audio track and ENGINE. Any writer that moves fewer than four is the bug."""
    src = _stripped(DOOR)
    assert "store.setMicMuted(" in src, "the icon's signal"
    assert "hb_mic_muted" in src, "the memory across a reload"
    assert "_transport(" in src, "the live audio track"
    assert "api.micState(" in src, "the engine's own copy of the fact"


def test_registering_a_transport_APPLIES_immediately():
    """The reconnect hole: the mute survived in localStorage and on screen, the newly published track came
    up open, and nothing re-asserted it."""
    src = _stripped(DOOR)
    m = re.search(r"function useTransport\([^)]*\)\s*\{(.*?)\n\}", src, flags=re.S)
    assert m, "useTransport must exist — it is how the session engines hand over their track"
    assert "applyNow(" in m.group(1), (
        "registering must APPLY — a freshly published track has to be born in the state the icon shows")


def test_the_door_remembers_what_LANDED_not_what_it_tried():
    """A request lost before a heartbeat exists behind it (⏻ off, no room) must be re-sent, not recorded as
    told — otherwise the module built to end the silent divergence contains one."""
    door = _stripped(DOOR)
    m = re.search(r"function applyNow\([^)]*\)\s*\{(.*?)\n\}", door, flags=re.S)
    assert m, "applyNow must exist — it is the re-assert"
    body = m.group(1)
    assert re.search(r"api\.micState\([^)]*\)\s*\.then", body), (
        "the write must be confirmed before it is remembered")
    assert not re.search(r"_lastSent\s*=\s*want;\s*api\.micState", body), (
        "remembering BEFORE the reply is what makes a lost request permanent")
    api = _stripped(FRONTEND / "app/services/api.js")
    assert re.search(r"micState\s*=[^\n]*\n?[^\n]*r\.ok", api), (
        "micState must report whether the engine took it")


def test_the_heartbeat_carries_the_state_every_beat():
    """Not only on change: a beat heals a divergence the client cannot detect (an engine restarted under a
    live tab comes back at its boot default and nobody would ever tell it otherwise)."""
    assert "mic.beat()" in _stripped(FRONTEND / "app/services/session-lk.js")
    api = _stripped(FRONTEND / "app/services/api.js")
    assert re.search(r"sessionHeartbeat\s*=\s*\(sid,\s*muted\)", api), (
        "the heartbeat must be able to carry the switch")


def test_the_livekit_publish_change_can_no_longer_fail_in_silence():
    """`setMicrophoneEnabled` returns a PROMISE — a sync try/catch cannot see its rejection, so a failed
    publish change was a silent divergence between the icon and the microphone."""
    src = _stripped(FRONTEND / "app/services/session-lk.js")
    i = src.find("setMicrophoneEnabled")
    assert i >= 0
    window = src[max(0, i - 200):i + 200]
    assert ".catch(" in window, "a rejected publish change must be caught, not left unhandled"
    assert "t.enabled" in src, (
        "the track's own enabled flag is what actually silences the wire, and it is synchronous — "
        "it must be set regardless of what the SDK call does")


# ── the ratchet: nobody walks around the door ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("needle,why", [
    ("setMicMuted(", "writes the icon's signal without touching the audio or the engine"),
    ("hb_mic_muted", "writes the persisted state without touching the audio or the engine"),
])
def test_only_the_door_writes_the_mic_state(needle, why):
    offenders = []
    for p in _sources():
        if p == DOOR or p == STORE:      # the door writes; the store DECLARES the signal
            continue
        if needle in _stripped(p):
            offenders.append(str(p.relative_to(FRONTEND)))
    assert offenders == [], (
        f"{offenders} {why}. Route it through `services/mic.js` — that module exists because four writers "
        f"did exactly this and the engine heard a microphone the operator had closed.")


def test_only_the_session_engines_touch_the_microphone_transport():
    """The other half of the same rule: reaching for the track from outside a session engine re-creates the
    divergence from the other side (audio moved, icon and engine unaware)."""
    allowed = {"app/services/session.js", "app/services/session-lk.js"}
    offenders = []
    for p in _sources():
        rel = str(p.relative_to(FRONTEND))
        if rel in allowed:
            continue
        src = _stripped(p)
        if "setMicrophoneEnabled" in src or re.search(r"getAudioTracks\(\)[^\n]*enabled", src):
            offenders.append(rel)
    assert offenders == [], f"{offenders} move the microphone behind the door's back"


def test_the_scan_actually_matched_something():
    """A pattern that stopped matching would guard nothing while staying green (V2-562's lesson)."""
    files = list(_sources())
    assert len(files) > 20, "the sweep found almost no frontend modules — the tree moved"
    assert any("setMicMuted(" in _stripped(p) for p in [DOOR]), "the door must still be a writer"
