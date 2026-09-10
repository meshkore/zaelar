"""Boot integrity + the ◉ monitor tells the truth (2026-09-10, operator review).

What happened, measured live: the engine was restarted WITHOUT `BRAIN=nucleo`, the profile default handed
the AgentSession a raw broker LLM plugin instead of the product's brain, every turn died on a provider
error, LiveKit closed the session — and the ◉ panel said «Todo bien» the whole time. Three families of
guarantees here:

  1. A bare `python -m server` boots THE PRODUCT (profile llm default = nucleo), never a baseline.
  2. A dead voice session is VISIBLE (health_state → /api/status row) and asks homeostasis for a recycle.
  3. The monitor reads the MACHINE's audio output (volume 0 / muted), and a dead TTS credential reddens
     the TTS row instead of hiding in the balance section.
"""
import asyncio
import json

import pytest


# ── 1) the boot default is the PRODUCT ───────────────────────────────────────────────────────────────────

def test_both_profiles_default_the_llm_to_nucleo():
    """The trap that bit: `remote.llm` was the raw broker plugin, so forgetting `BRAIN=nucleo` silently
    booted a different product (no FlashBrain, no memory, no tools, no relay) while /api/brain kept
    answering «nucleo» from its own knob. The baselines stay one env var away (BRAIN=direct/local)."""
    from voice.engine.core.profile import _DEFAULTS
    assert _DEFAULTS["remote"]["llm"] == "nucleo"
    assert _DEFAULTS["local"]["llm"] == "nucleo"


def test_without_BRAIN_the_provider_resolves_to_nucleo(monkeypatch):
    monkeypatch.delenv("BRAIN", raising=False)
    monkeypatch.delenv("ZAELAR_LLM_PROVIDER", raising=False)
    from voice.engine.core.config import _llm_provider_default
    assert _llm_provider_default() == "nucleo"


def test_BRAIN_env_still_wins_for_the_baselines(monkeypatch):
    monkeypatch.setenv("BRAIN", "direct")
    from voice.engine.core.config import _llm_provider_default
    assert _llm_provider_default() == "direct"


# ── 2) a dead session is visible and asks for a recycle ─────────────────────────────────────────────────

def _stripped(path):
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[4] / path
    return re.sub(r"(?m)#.*$", "", src.read_text(encoding="utf-8"))


def test_the_session_close_handler_records_the_death_and_asks_for_the_recycle():
    """Wiring guard on the real handler (comment-stripped): the three duties live in `_on_close` — say it
    where the monitor looks, say it on the timeline, ask homeostasis to recycle."""
    text = _stripped("voice/engine/pipeline/agent.py")
    i = text.find('def _on_close(')
    j = text.find("def ", i + 10)
    body = text[i:j]
    assert 'health_state.record("voice", "dead"' in body
    assert "homeostasis.request_recycle(" in body
    assert 'emit("alert"' in body.replace("_emit(", "emit(")


def test_a_session_that_starts_clears_the_recorded_death():
    text = _stripped("voice/engine/pipeline/agent.py")
    i = text.find("await session.start(room=ctx.room, agent=agent)")
    assert i >= 0
    assert 'health_state.clear("voice")' in text[i:i + 400], (
        "a living session supersedes the death record — otherwise the row stays red for 10 minutes of TTL")


def test_api_status_says_the_voice_session_died(monkeypatch):
    from voice import health_state
    from server.voice_api import status
    health_state.record("voice", "dead", "unrecoverable LLM error")
    try:
        body = json.loads(asyncio.run(status()).body)
        row = next(it for it in body["items"] if it["key"] == "voice")
        assert row["state"] == "error"
        assert "MURIÓ" in row["detail"]
    finally:
        health_state.clear("voice")


def test_the_client_merge_respects_a_server_side_death():
    """StatusPanel overwrites the voice row with the browser's live view — which is exactly how a dead
    AgentSession stayed invisible (the browser's room stays connected). An error state must survive."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "frontend/app/components/StatusPanel.js").read_text(encoding="utf-8")
    assert 'it.state !== "error"' in src


def test_the_speaker_truth_reaches_the_voice_row():
    """«me escucha pero no me habla» has two silent causes the browser already knows (blocked playback,
    the operator's own 🔊 mute) — voiceStatus must read both signals."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[4] / "frontend/app/services/status.js").read_text(encoding="utf-8")
    assert "store.audioBlocked()" in src and "store.botMuted()" in src


# ── 3) the machine's own audio output ────────────────────────────────────────────────────────────────────

def _fake_run(stdout):
    class R:
        pass
    r = R(); r.stdout = stdout
    return lambda *a, **k: r


def test_system_audio_parses_the_macos_answer(monkeypatch):
    from server import system_audio as SA
    monkeypatch.setattr(SA.sys, "platform", "darwin")
    monkeypatch.setattr(SA.subprocess, "run",
                        _fake_run("output volume:54, input volume:75, alert volume:75, output muted:false"))
    SA._cache = None
    assert SA.output_status() == {"volume": 54, "muted": False}
    assert SA.status_item()["state"] == "ok"


@pytest.mark.parametrize("stdout,why", [
    ("output volume:0, input volume:75, alert volume:75, output muted:false", "volume at zero"),
    ("output volume:54, input volume:75, alert volume:75, output muted:true", "muted"),
])
def test_system_audio_warns_when_nothing_can_sound(monkeypatch, stdout, why):
    from server import system_audio as SA
    monkeypatch.setattr(SA.sys, "platform", "darwin")
    monkeypatch.setattr(SA.subprocess, "run", _fake_run(stdout))
    SA._cache = None
    item = SA.status_item()
    assert item["state"] == "warn", why


def test_an_unmeasured_os_gets_no_row_instead_of_a_fake_green(monkeypatch):
    from server import system_audio as SA
    monkeypatch.setattr(SA.sys, "platform", "linux")
    SA._cache = None
    assert SA.status_item() is None


# ── 4) a dead TTS credential reddens the TTS row ─────────────────────────────────────────────────────────

def _fake_httpx_get(status_code, text):
    class R:
        pass
    r = R(); r.status_code = status_code; r.text = text
    return lambda *a, **k: r


def test_a_genuinely_dead_elevenlabs_key_records_tts_auth(monkeypatch):
    from config import balances
    from voice import health_state
    health_state.clear("tts")
    monkeypatch.setattr(balances.httpx, "get",
                        _fake_httpx_get(401, '{"detail":{"status":"invalid_api_key"}}'))
    out = balances._probe_elevenlabs("k")
    try:
        assert out["state"] == "error"
        err = health_state.get("tts")
        assert err and err["kind"] == "auth"
    finally:
        health_state.clear("tts")


def test_a_scoped_key_that_can_speak_records_nothing(monkeypatch):
    """Measured live 2026-09-10: the operator's key answers 401 `missing_permissions user_read` on the
    balance endpoint and 200 on a real synthesis — an alert here would cry wolf over a working voice."""
    from config import balances
    from voice import health_state
    health_state.clear("tts")
    monkeypatch.setattr(balances.httpx, "get",
                        _fake_httpx_get(401, '{"detail":{"status":"missing_permissions",'
                                             '"message":"missing the permission user_read"}}'))
    out = balances._probe_elevenlabs("k")
    assert out["state"] == "unknown"
    assert health_state.get("tts") is None
