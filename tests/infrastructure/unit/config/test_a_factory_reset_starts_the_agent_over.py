"""«Quiero inicializar un agente nuevo en otro idioma, todo de cero» (V2-670, 2026-09-11).

MEASURED before building anything, on the operator's own install: ticking BOTH existing checkboxes of the
Reset dialog left an agent that still spoke Spanish with the voice already chosen, and the first-run language
ceremony never fired. One line explains it — `i18n.init.detect.should_detect()` returns True only while
`stt_language` is EMPTY in `config/settings.json`, and that file sat in `reset-memory.sh`'s KEEP_ALWAYS list,
untouched by either box.

Deleting the file whole is the WRONG fix, also measured: the default profile is `remote`, whose defaults are
Voxtral + Cartesia, so a wipe silently swaps which paid provider does STT and TTS — underneath a test that is
itself SPOKEN. So the split is by OWNERSHIP: the MACHINE's setup survives, the AGENT's identity does not.

These tests never run the script (it deletes things); they check the CONTRACT: the split is complete, the
surgery does what it says, and the dialog's four boxes actually reach the four flags.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "scripts" / "reset-memory.sh"
API = ROOT / "server" / "voice_api.py"
TOPBAR = ROOT / "frontend" / "app" / "components" / "TopBar.js"
SESSION = ROOT / "frontend" / "app" / "services" / "session-lk.js"


# ── the split is COMPLETE — a knob added later must not survive by having been added later ────────────────

def test_every_known_setting_is_classified_as_the_machine_or_the_agent():
    """The V2-548 class, applied here: a seed list falls behind on its own, silently. A new preference that
    nobody classified would quietly outlive a factory reset and make the next «clean» test impure."""
    from config import settings as st
    known = set(st.ENV_KEYS) | set(st.BOOL_DEFAULTS)
    unclassified = sorted(known - st.INSTALL_KEYS - st.AGENT_KEYS)
    assert not unclassified, (
        f"these knobs belong to neither the installation nor the agent: {unclassified} — decide which, "
        "because 'factory reset' cannot mean 'whatever nobody got round to listing'")
    overlap = sorted(st.INSTALL_KEYS & st.AGENT_KEYS)
    assert not overlap, f"a knob cannot be both: {overlap}"


def test_the_language_gate_is_on_the_AGENT_side():
    """`stt_language` is not a preference among others: it is THE gate. If it survives, the ceremony that
    this whole feature exists to trigger never fires, and the reset looks like it worked."""
    from config import settings as st
    assert "stt_language" in st.AGENT_KEYS
    assert "stt_language" not in st.INSTALL_KEYS


def test_which_paid_provider_does_the_voice_SURVIVES():
    """The onboarding ceremony is SPOKEN. A reset that also swaps the microphone stack turns a language test
    into a debugging session about why nothing is audible."""
    from config import settings as st
    for k in ("stt_provider", "tts_provider", "zaelar_profile"):
        assert k in st.INSTALL_KEYS, f"{k} is machine setup and must survive a factory reset"


# ── the surgery ───────────────────────────────────────────────────────────────────────────────────────────

def test_factory_reset_keeps_the_setup_and_drops_everything_else(tmp_path, monkeypatch):
    from config import settings as st
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({
        "stt_provider": "deepgram", "tts_provider": "elevenlabs", "zaelar_profile": "remote",
        "stt_language": "es", "assistant_voice": "ef_dora", "wizard_done": True,
        "wallpaper": {"url": "https://x/y.jpg"}, "attention_mode": "smart",
        "some_future_knob": "whatever",
    }), encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    out = st.factory_reset()
    left = json.loads(f.read_text(encoding="utf-8"))
    # `wizard_done` moved here in V2-671 and the reason is the whole point: on the AGENT side, dropping it
    # made the first-run wizard fire after this very reset, and the wizard rewrote settings.json AND v2.json
    # together — so the three keys above were preserved and then overwritten seconds later.
    assert set(left) == {"stt_provider", "tts_provider", "zaelar_profile", "wizard_done"}, left
    assert left["stt_provider"] == "deepgram", "the machine's own setup must come through untouched"
    assert "stt_language" in out["dropped"] and "some_future_knob" in out["dropped"], (
        "an UNKNOWN key is dropped: 'as if for the first time' cannot preserve what nobody recognised")


def test_factory_reset_on_a_missing_file_does_not_explode(tmp_path, monkeypatch):
    from config import settings as st
    monkeypatch.setattr(st, "SETTINGS_FILE", tmp_path / "nope.json")
    assert st.factory_reset()["dropped"] == []


# ── the script's own promises ─────────────────────────────────────────────────────────────────────────────

def _array(script: str, name: str) -> list[str]:
    """The QUOTED entries of a bash array, with comments stripped.

    V2-670: the first version of these tests read the raw block, so commenting a path OUT left the string
    sitting in the file and the guard stayed green over a disarmed script — the same prose-vs-code trap paid
    hours earlier in `test_filler_path_never_writes_last_reply`. A guard that a comment can satisfy is not a
    guard.
    """
    block = script.split(f"{name}=(")[1].split("\n)")[0]
    out: list[str] = []
    for line in block.splitlines():
        code = line.split("#", 1)[0]
        out += re.findall(r'"([^"]+)"', code)
    return out


@pytest.fixture(scope="module")
def script() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_the_script_offers_both_new_flags(script):
    assert "--factory)" in script and "--wipe-files)" in script


def test_settings_surgery_is_NOT_reimplemented_in_bash(script):
    """One source for who owns which knob. Bash re-encoding the list is how the two drift apart."""
    assert "from config.settings import factory_reset" in script
    assert "stt_language" not in script.split("# Usage:")[1].split("set -euo")[1], (
        "the executable half of the script must not name individual knobs")


def test_episodic_blobs_die_WITH_the_database(script):
    """They are memory's payload — the row that points at the blob lives in zaelar.db. Split across two
    checkboxes you get either orphan files or rows pointing at nothing. The array used to be EMPTY while the
    comment above it already claimed episodic was memory: 37 files survived every reset on the real install."""
    assert "memory/_data/episodic" in _array(script, "MEMORY_DIRS_CONTENTS")


def test_the_credentials_box_reaches_where_the_email_password_actually_lives(script):
    """The dialog has always promised «widget credentials», and `config/connectors.json` — the email app
    password, the Telegram api_id/hash — was in KEEP_ALWAYS. Half of them survived."""
    assert "config/connectors.json" in _array(script, "CRED_PATHS")
    assert "config/connectors.json" not in _array(script, "KEEP_ALWAYS")


def test_the_api_keys_and_model_routing_are_NEVER_touched(script):
    keep = _array(script, "KEEP_ALWAYS")
    for path in (".env", ".meshkore/credentials", "config/v2.json"):
        assert path in keep, f"{path} must survive every box — it is the machine's, not the agent's"


def test_the_browser_cookie_profile_is_never_swept_by_the_widget_sweep(script):
    """The widget sweep was broadened from `state.json` to `*.json`; depth must stay EXACTLY 2 so
    `widgets/_data/navegador/profile/…` (depth 3+) is still out of reach."""
    m = re.search(r"find widgets/_data -mindepth (\d) -maxdepth (\d) -name '\*\.json'", script)
    assert m and m.group(1) == "2" and m.group(2) == "2", "the widget json sweep must stay at exact depth 2"


# ── the four boxes reach the four flags ───────────────────────────────────────────────────────────────────

def test_the_endpoint_maps_each_box_to_its_flag():
    src = API.read_text(encoding="utf-8")
    assert 'p.get("wipe_profile")' in src and 'p.get("wipe_files")' in src
    assert '" --factory" if wipe_profile' in src and '" --wipe-files" if wipe_files' in src
    assert "not wipe_profile and not wipe_files" in src, (
        "ticking only a new box must still take the RESTART path — deleting settings/library needs the "
        "process dead for the same reason memory does")


def test_the_dialog_paints_four_boxes_and_forwards_all_four():
    top = TOPBAR.read_text(encoding="utf-8")
    for ref in ("memEl", "credEl", "profEl", "filesEl"):
        assert f"(el) => ({ref} = el)" in top, f"the {ref} checkbox is not in the dialog"
    assert "session.resetFull({ wipeMemory, wipeCredentials, wipeProfile, wipeFiles })" in top
    ses = SESSION.read_text(encoding="utf-8")
    assert "wipe_profile: wipeProfile" in ses and "wipe_files: wipeFiles" in ses, (
        "the transport must carry them or the box is decoration")


def test_both_new_boxes_have_words_in_both_languages():
    keys = ("reset.confirm.wipeProfile", "reset.confirm.wipeFiles")
    for code in ("es", "en"):
        d = json.loads((ROOT / "i18n" / "bundles" / f"{code}.json").read_text(encoding="utf-8"))
        for k in keys:
            assert d.get(k, "").strip(), f"[{code}] {k} missing — an unlabelled checkbox is a trap"
