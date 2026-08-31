"""test_profiles.py — coordinated LOCAL/CLOUD profiles (V2-040). Verifies: normalization + aliases, the coordinated
package, the derived requirements, and that `apply` writes to BOTH stores (settings + v2) without leaking secrets.
Run: .venv/bin/pytest tests/infrastructure/unit/config/test_profiles.py
"""
import config.profiles as profiles


def test_canon_aliases_and_unknown():
    assert profiles.canon("cloud") == "cloud"
    assert profiles.canon("LOCAL") == "local"
    assert profiles.canon("remote") == "cloud"          # compatibility alias
    assert profiles.canon("noexiste") == profiles.DEFAULT   # unknown → default (does NOT silently downgrade to remote)
    assert profiles.canon("") == profiles.DEFAULT


def test_two_shipped_profiles():
    assert set(profiles.names()) == {"local", "cloud"}
    loc, cloud = profiles.get("local"), profiles.get("cloud")
    assert loc["voice"]["stt_provider"] == "whisper_local"
    assert loc["v2"]["fast"]["provider"] == "ollama"
    assert loc["v2"]["memory"]["embed_provider"] == "ollama"
    assert cloud["voice"]["tts_provider"] == "elevenlabs"
    assert cloud["v2"]["fast"]["provider"] == "aimlapi"
    assert cloud["engine_profile"] == "remote"          # the engine still uses 'remote'


def test_public_has_no_secret_fields():
    blob = repr(profiles.public())
    assert "api_key" not in blob                         # the package contains no secrets (the keys are kept separately)
    names = {p["name"] for p in profiles.public()}
    assert names == {"local", "cloud"}


def test_requirements_local_vs_cloud():
    loc = profiles.requirements("local")
    assert loc["needs_ollama"] is True
    assert loc["needs_local_accel"] is True
    # the required models come from the package ITSELF (fast + embed + CORE)
    assert any("qwen2.5" in m for m in loc["ollama_models"])
    assert "embeddinggemma" in loc["ollama_models"]

    cloud = profiles.requirements("cloud")
    assert cloud["needs_ollama"] is False
    assert cloud["needs_local_accel"] is False
    assert "aimlapi" in cloud["credentials"]             # the doctor catalog marks aimlapi as cloud-only
    assert cloud["needs_claude_cli"] is True             # SlowBrain uses Claude in both profiles


def test_apply_writes_both_stores(tmp_path, monkeypatch):
    """`apply` must update settings.json (voice) AND v2.json (routing/memory), in coordination, without breaking."""
    import config.settings as settings
    import config.v2 as v2
    # isolate both stores in temporary files
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")
    # avoid the heavy voice-alignment work (voices/language) of the real update
    monkeypatch.setattr(settings, "effective", lambda: {"knobs": [], "free_text": [], "voices_by_provider": {}})

    res = profiles.apply("local")
    assert res["profile"] == "local"
    assert res["applied"]["v2"]["ok"] is True
    # v2: FlashBrain ended up on ollama and memory on local
    assert v2.get("fast")["provider"] == "ollama"
    assert v2.get("memory")["embed_provider"] == "ollama"
    assert v2.get("flags")["brain"] == "nucleo"
    # settings: local STT/TTS + the persisted engine profile
    assert settings.get("stt_provider") == "whisper_local"
    assert settings.get("zaelar_profile") == "local"
    assert profiles.active() == "local"

    # switching to cloud re-coordinates everything
    profiles.apply("cloud")
    assert v2.get("fast")["provider"] == "aimlapi"
    assert settings.get("tts_provider") == "elevenlabs"
    assert settings.get("zaelar_profile") == "remote"
    assert profiles.active() == "cloud"


def test_apply_never_persists_a_secret(tmp_path, monkeypatch):
    import config.settings as settings
    import config.v2 as v2
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")
    monkeypatch.setattr(settings, "effective", lambda: {"knobs": [], "free_text": [], "voices_by_provider": {}})
    profiles.apply("cloud")
    # the package sets api_key="" → it never writes a secret; the public view confirms this
    assert v2.public("fast")["api_key_set"] is False
