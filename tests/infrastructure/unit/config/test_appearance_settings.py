"""The appearance choice belongs to the ACCOUNT, and what it stores can only be a color, a size step or a
font id (V2-617). settings.json is the durable copy behind the ⚙ Apariencia tab; the stored dict is echoed
into inline CSS custom properties on every client that loads the account, so the sanitizer here is a
security seam, not tidiness — a value that can carry `;}` or a URL is a stored style injection."""
import pytest


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    import config.settings as settings
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    return settings


def test_the_profile_and_custom_knobs_persist_and_read_back(isolated):
    s = isolated
    r = s.update({"theme_profile": "ambar", "theme_custom": {"accent": "#22AA66", "fs": "l", "font": "serif"}})
    assert "theme_profile" in r["applied"] and "theme_custom" in r["applied"]
    assert r["needs_reconnect"] is False, "appearance applies live on the client — never a voice reconnect"
    assert s.theme() == {"profile": "ambar", "custom": {"accent": "#22AA66", "fs": "l", "font": "serif"}}


def test_hostile_values_are_dropped_not_stored(isolated):
    s = isolated
    s.update({"theme_profile": "x" * 99, "theme_custom": {
        "accent": "red;}body{background:url(//evil)", "fs": "xl", "font": "a b", "extra": "<script>"}})
    th = s.theme()
    assert th["profile"] == "", "an over-long profile slug must not persist"
    assert th["custom"] == {}, f"every malformed knob is dropped, unknown keys included: {th}"


def test_a_stored_dirty_dict_is_sanitized_on_the_way_out(isolated):
    """The read side cleans too: a settings.json edited by hand (or written by an older build) must not
    hand a raw value to the client."""
    s = isolated
    s._write({"theme_profile": "grafito", "theme_custom": {"accent": "#GGGGGG", "fs": "s", "junk": 1}})
    assert s.theme() == {"profile": "grafito", "custom": {"fs": "s"}}


def test_the_settings_get_carries_the_theme_for_the_boot_reconcile(isolated):
    """services/theme.js reconciles from /api/settings GET → effective() must carry the block. effective()
    imports the live voice engine, so the contract is pinned at the SOURCE."""
    import pathlib
    src = pathlib.Path("config/settings.py").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if l.strip().startswith("return {") and "voices_by_provider" in l)
    assert '"theme": theme()' in line, "effective() must include the persisted appearance"
