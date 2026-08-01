"""test_profiles.py — perfiles LOCAL/CLOUD coordinados (V2-040). Verifica: normalización + alias, el paquete
coordinado, los requisitos derivados, y que `apply` escribe en AMBOS stores (settings + v2) sin filtrar secretos.
Ejecutar: .venv/bin/pytest tests/infrastructure/unit/config/test_profiles.py
"""
import config.profiles as profiles


def test_canon_aliases_and_unknown():
    assert profiles.canon("cloud") == "cloud"
    assert profiles.canon("LOCAL") == "local"
    assert profiles.canon("remote") == "cloud"          # alias de compatibilidad
    assert profiles.canon("noexiste") == profiles.DEFAULT   # desconocido → default (NO degrada mudo a remote)
    assert profiles.canon("") == profiles.DEFAULT


def test_two_shipped_profiles():
    assert set(profiles.names()) == {"local", "cloud"}
    loc, cloud = profiles.get("local"), profiles.get("cloud")
    assert loc["voice"]["stt_provider"] == "whisper_local"
    assert loc["v2"]["fast"]["provider"] == "ollama"
    assert loc["v2"]["memory"]["embed_provider"] == "ollama"
    assert cloud["voice"]["tts_provider"] == "elevenlabs"
    assert cloud["v2"]["fast"]["provider"] == "aimlapi"
    assert cloud["engine_profile"] == "remote"          # el motor sigue hablando 'remote'


def test_public_has_no_secret_fields():
    blob = repr(profiles.public())
    assert "api_key" not in blob                         # el paquete no lleva secretos (las keys van aparte)
    names = {p["name"] for p in profiles.public()}
    assert names == {"local", "cloud"}


def test_requirements_local_vs_cloud():
    loc = profiles.requirements("local")
    assert loc["needs_ollama"] is True
    assert loc["needs_local_accel"] is True
    # los modelos requeridos salen del PROPIO paquete (fast + embed + CORAZÓN)
    assert any("qwen2.5" in m for m in loc["ollama_models"])
    assert "embeddinggemma" in loc["ollama_models"]

    cloud = profiles.requirements("cloud")
    assert cloud["needs_ollama"] is False
    assert cloud["needs_local_accel"] is False
    assert "aimlapi" in cloud["credentials"]             # el catálogo de doctor marca aimlapi como de cloud
    assert cloud["needs_claude_cli"] is True             # el SlowBrain usa claude en ambos perfiles


def test_apply_writes_both_stores(tmp_path, monkeypatch):
    """`apply` debe tocar settings.json (voz) Y v2.json (routing/memoria), coordinados, sin reventar."""
    import config.settings as settings
    import config.v2 as v2
    # aísla ambos stores a ficheros temporales
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(v2, "_PATH", tmp_path / "v2.json")
    # evita el trabajo pesado de la alineación de voz (voces/idioma) del update real
    monkeypatch.setattr(settings, "effective", lambda: {"knobs": [], "free_text": [], "voices_by_provider": {}})

    res = profiles.apply("local")
    assert res["profile"] == "local"
    assert res["applied"]["v2"]["ok"] is True
    # v2: el FlashBrain quedó en ollama y la memoria en local
    assert v2.get("fast")["provider"] == "ollama"
    assert v2.get("memory")["embed_provider"] == "ollama"
    assert v2.get("flags")["brain"] == "nucleo"
    # settings: STT/TTS locales + el perfil de motor persistido
    assert settings.get("stt_provider") == "whisper_local"
    assert settings.get("zaelar_profile") == "local"
    assert profiles.active() == "local"

    # cambiar a cloud re-coordina todo
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
    # el paquete fija api_key="" → nunca escribe un secreto; la vista pública lo confirma
    assert v2.public("fast")["api_key_set"] is False
