"""V2-654 — the microphone switch: ONE fact, and everything that acts on heard audio obeys it.

Measured 2026-09-10 (session 85eec898): the mute lived only in the browser, four of its six writers moved
the icon and never the audio track, and the engine had no notion of a microphone switch at all — so it
transcribed the operator for seven minutes with the 🎤 shut and escalated an errand off what it heard.

These cases pin the ENGINE half: the holder, the route, the heartbeat re-assert, and the turn gate — plus
the one exemption that is the whole point of muting (typing), and the direction each failure must take.
"""
import pytest

from voice import attention, mic_input


@pytest.fixture(autouse=True)
def _fresh_switch():
    mic_input.reset()
    attention.reset()
    yield
    mic_input.reset()
    attention.reset()


# ── the holder ────────────────────────────────────────────────────────────────────────────────────────────

def test_the_boot_default_is_OPEN():
    """A stale or absent client must never be able to leave the agent deaf forever — deafness is the OTHER
    failure the same session paid for (16 turns discarded while the operator asked what was wrong)."""
    assert mic_input.is_muted() is False


def test_muted_is_STICKY_until_it_is_explicitly_lifted():
    """A client that mutes and then dies leaves the engine muted: the safe side of that accident."""
    mic_input.set_muted(True, source="orb")
    assert mic_input.is_muted() is True
    assert mic_input.snapshot()["source"] == "orb"
    mic_input.set_muted(True, source="heartbeat")
    assert mic_input.is_muted() is True
    mic_input.set_muted(False, source="orb")
    assert mic_input.is_muted() is False


def test_only_a_real_change_is_worth_an_event(monkeypatch):
    """The heartbeat re-asserts the same value every ~4s — logging each one would bury the timeline in
    fifteen rows a minute that say nothing happened."""
    import voice.observer as obs
    seen = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        seen.append((kind, label, (extra or {}).get("muted"))))
    assert mic_input.set_muted(True, source="orb")["changed"] is True
    assert mic_input.set_muted(True, source="heartbeat")["changed"] is False
    assert mic_input.set_muted(True, source="heartbeat")["changed"] is False
    assert mic_input.set_muted(False, source="orb")["changed"] is True
    assert [s[2] for s in seen] == [True, False]
    assert all(k == "mic" for k, _, _ in seen)


def test_the_switch_never_dies_with_the_observer(monkeypatch):
    """It is called from a route handler AND from the turn's hot path — neither may die because
    observability is unavailable."""
    import voice.observer as obs

    def _boom(*a, **k):
        raise RuntimeError("observer down")

    monkeypatch.setattr(obs, "emit", _boom)
    assert mic_input.set_muted(True)["muted"] is True
    assert mic_input.is_muted() is True


# ── the turn gate ─────────────────────────────────────────────────────────────────────────────────────────

def test_a_typed_turn_is_exempt_EXACTLY_ONCE():
    """Muting the mic to TYPE is the use case, so a typed turn must pass a closed switch. One-shot and not
    a time window: with a window, typing and then speaking walks the spoken turn through the closed mic."""
    mic_input.set_muted(True, source="orb")
    attention.note_typed()
    assert attention.consume_typed() is True     # the typed turn
    assert attention.consume_typed() is False    # anything after it is audio


def test_the_exemption_does_not_survive_a_reset():
    attention.note_typed()
    attention.reset()
    assert attention.consume_typed() is False


def test_the_window_based_fact_is_untouched_by_the_one_shot():
    """`was_typed()` is the mute backstop's (V2-646) and wants a WINDOW — consuming the gate's exemption
    must not blind it."""
    attention.note_typed()
    attention.consume_typed()
    assert attention.was_typed(within_s=45.0) is True


def test_a_muted_turn_is_swallowed_and_an_open_one_is_not(monkeypatch):
    import voice.observer as obs
    seen = []
    monkeypatch.setattr(obs, "emit", lambda kind, label, text="", role="", extra=None:
                        seen.append((kind, text)))
    assert mic_input.blocks_turn("cierra el widget") is False, "an open mic swallows nothing"
    assert seen == [], "an open mic leaves no row: the timeline records the switch, not every heard turn"
    mic_input.set_muted(True, source="orb")
    assert mic_input.blocks_turn("cierra el widget") is True
    assert seen[-1][0] == "mic"
    assert "cierra el widget" in seen[-1][1], (
        "the discarded text is the EVIDENCE that the browser kept publishing over a shut icon — "
        "without it, that divergence cost seven minutes to see")


def test_a_typed_turn_passes_a_CLOSED_switch_but_the_audio_behind_it_does_not(monkeypatch):
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: None)
    mic_input.set_muted(True, source="orb")
    attention.note_typed()
    assert mic_input.blocks_turn("¿qué hora es?") is False, "muting to type IS the use case"
    assert mic_input.blocks_turn("¿qué hora es?") is True, "the next turn is audio again"


def test_the_switch_and_the_WAKE_WORD_MODE_are_two_different_axes(monkeypatch):
    """Operator's rule (2026-09-10): the 🤖 wake-word mode is what makes a permanently open microphone
    livable — audio arrives, is transcribed, and the attention rules decide turn by turn what was addressed
    to us. This switch is the OTHER axis, his own hand shutting the input, and neither may be written in
    terms of the other: no wake word lifts a hard close, and lifting the close changes no attention state.
    """
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: None)
    monkeypatch.setenv("ZAELAR_ATTENTION", "smart")

    mic_input.set_muted(True, source="orb")
    assert mic_input.blocks_turn("zaelar, enséñame la agenda") is True, (
        "a wake word may not lift a microphone the operator closed")

    before = attention.evaluate("enséñame la agenda").directed
    mic_input.blocks_turn("zaelar, enséñame la agenda")
    assert attention.evaluate("enséñame la agenda").directed == before, (
        "a swallowed turn must not open or refresh a conversation window on its way out")

    mic_input.set_muted(False, source="orb")
    assert mic_input.blocks_turn("enséñame la agenda") is False, "the switch is open again"
    assert attention.evaluate("enséñame la agenda").directed is False, (
        "…and the mode he had is the mode he gets back: lifting the close grants no attention of its own")


def test_the_gate_sits_ABOVE_the_attention_gate_and_below_nothing_else():
    """Structural: a closed mic is not an opinion about who was being addressed, so no conversation window
    and no wake word may lift it — the check has to run BEFORE `evaluate_content` is consulted."""
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[3] / "voice/engine/llm/providers/nucleo.py"
    text = re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))
    gate = text.find("mic_input.blocks_turn")
    attn = text.find("attention.evaluate_content")
    assert gate >= 0, "the turn path must consult the microphone switch"
    assert attn >= 0 and gate < attn, (
        "the mic gate must run BEFORE the attention gate — otherwise a wake word or an open "
        "conversation window would walk audio through a microphone the operator closed")


# ── the two doors that write it ──────────────────────────────────────────────────────────────────────────

def test_the_route_writes_the_switch_and_reports_it():
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from server.voice_api import router

    app = FastAPI()
    app.include_router(router)
    c = TestClient(app)

    assert c.post("/api/mic", json={"muted": True, "src": "orb"}).json()["muted"] is True
    assert mic_input.is_muted() is True
    body = c.get("/api/mic").json()
    assert body["muted"] is True and body["source"] == "orb"
    c.post("/api/mic", json={"muted": False, "src": "orb"})
    assert mic_input.is_muted() is False


def test_a_heartbeat_reasserts_the_switch_and_an_older_client_still_beats():
    """The beat is the cheapest correction channel there is — it heals a divergence the client cannot even
    detect (an engine restarted under a live tab comes back at the boot default). `muted` stays OPTIONAL so
    a client that never sends it beats exactly as before."""
    from server.livekit_api import session_heartbeat

    assert session_heartbeat({"sid": "tab-1", "muted": True})["ok"] is True
    assert mic_input.is_muted() is True
    assert session_heartbeat({"sid": "tab-1"})["ok"] is True
    assert mic_input.is_muted() is True, "a beat with no `muted` must not lift the switch"
    assert session_heartbeat({"sid": "tab-1", "muted": False})["ok"] is True
    assert mic_input.is_muted() is False


def test_a_non_boolean_muted_is_ignored_rather_than_guessed():
    """Silence and garbage both mean «this beat carries no opinion» — reading either as a value would flip
    a switch nobody touched."""
    from server.livekit_api import session_heartbeat
    mic_input.set_muted(True, source="orb")
    session_heartbeat({"sid": "tab-1", "muted": "yes"})
    assert mic_input.is_muted() is True
    session_heartbeat({"sid": "tab-1", "muted": None})
    assert mic_input.is_muted() is True
