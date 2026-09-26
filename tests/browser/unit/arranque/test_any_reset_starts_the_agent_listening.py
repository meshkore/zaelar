"""ANY reset puts the switches back to a fresh install's position (operator, 2026-09-25).

*«Cuando después de un reset o una inicialización de cero, el agente empieza arrancado. Es decir, el orbe
escuchando, el micrófono activo, el altavoz activo y el word activation desactivado… Aunque estuviera antes
diferente, en cuanto hago un reset, todas esas variables de estado pasan al estado inicial.»*

Three places hold those switches and each is reset here: the ⏻ (`sys_kv run:state`) and the attention mode
(settings.json) by scripts/reset-memory.sh on EVERY run — they were only reset under --factory — and the
browser's own mute/dock keys by the wipe epoch (first-run.js::takeoverOnReset, the .mjs contract next door),
which both shells must call.
"""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
SCRIPT = (ROOT / "scripts/reset-memory.sh").read_text(encoding="utf-8")


def _outside_factory_block(needle: str) -> bool:
    """True when `needle` runs on every reset: it appears after the --factory block has closed."""
    m = re.search(r'^if \[\[ "\$FACTORY" == "1" \]\]; then\n(.*?)^fi\n', SCRIPT, re.S | re.M)
    assert m, "the factory block moved — update this test"
    return needle in SCRIPT[m.end():] and needle not in m.group(1)


def test_the_power_switch_starts_over_on_every_reset():
    assert _outside_factory_block("kv_del('run:state')"), (
        "the ⏻ must be cleared on EVERY reset — with memory kept, a ⏻ off from before survives it")


def test_the_attention_mode_starts_over_on_every_reset():
    assert _outside_factory_block("reset_switches()"), "the wake word must be off after ANY reset"


def test_reset_switches_drops_the_attention_keys_and_nothing_else(tmp_path, monkeypatch):
    from config import settings
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"attention_mode": "wakeword", "attention_window": "3",
                             "assistant_voice": "CwhRBWXzGAHq8TQ4Fs17",     # aligned with en-US, and not the pin
                             "stt_language": "es", "stt_provider": "x"}), encoding="utf-8")
    monkeypatch.setattr(settings, "SETTINGS_FILE", f)
    assert settings.reset_switches() == ["assistant_voice", "attention_mode", "attention_window"]
    assert json.loads(f.read_text(encoding="utf-8")) == {"stt_language": "es", "stt_provider": "x"}
    assert settings.SWITCH_KEYS <= settings.AGENT_KEYS, "a switch is the agent's, never the installation's"


def test_the_reset_epoch_has_one_owner_in_the_browser():
    """V2-773 audit: `desktop.js::restore` and `first-run.js::takeoverOnReset` both fetched the epoch at boot
    and both recorded it under `hb_wipe` — whichever answered first spent the other's turn, and when the
    desktop won, the mic and speaker mutes survived the reset. One key per reader, and the desktop's sits in
    the swept namespace so it re-runs (and clears the SERVER state) after the takeover's reload."""
    fr = (ROOT / "frontend/app/core/first-run.js").read_text(encoding="utf-8")
    dk = (ROOT / "frontend/app/widgets/desktop.js").read_text(encoding="utf-8")
    assert 'const WIPE_KEY = "hb_wipe"' in fr
    assert 'setItem("hb_wipe"' not in dk and '"hb_wipe"' not in dk, "desktop.js must not touch first-run's key"
    assert 'localStorage.getItem("hb_desktop_epoch")' in dk and 'localStorage.setItem("hb_desktop_epoch"' in dk
    assert "hb_desktop_epoch".startswith("hb_"), "the desktop's key must be swept by the takeover"


def test_the_default_attention_mode_has_no_wake_word():
    src = (ROOT / "config/settings.py").read_text(encoding="utf-8")
    assert 'os.getenv("ZAELAR_ATTENTION", "always")' in src, "dropping the key must land on «always»"


def test_both_shells_obey_the_reset_epoch():
    for shell in ("frontend/app/main.js", "frontend/mobile/app/main.js"):
        src = (ROOT / shell).read_text(encoding="utf-8")
        assert "firstRun.takeoverOnReset(" in src and "/api/desktop/epoch" in src, shell
        assert re.search(r'import \* as firstRun from "[./]*(app/)?core/first-run\.js', src), shell
