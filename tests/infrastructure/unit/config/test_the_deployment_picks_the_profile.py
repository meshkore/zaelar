"""«El paso de si quiero una instalación local o remota es absurdo» (V2-671, 2026-09-11).

MEASURED on the operator's own install, right after a factory reset: his engine came back up on
`qwen2.5:14b-instruct` over Ollama with `whisper_local` + `kokoro_local`, instead of the canonical table's
`deepseek-v4-pro` + `deepgram` + `elevenlabs`. Nothing in the reset did that. The chain was:

  factory reset dropped `wizard_done`  →  the first-run wizard fired  →  it recommended `local` (Apple
  Silicon with Ollama running)  →  `profiles.apply()` writes settings.json AND config/v2.json together.

So the four install keys V2-670 deliberately preserved were preserved, and then overwritten twenty seconds
later — along with the model routing the Reset dialog promises in writing is never touched.

Two things are pinned here, and they are different in kind:

  1. NOBODY IS ASKED. The deployment knows where it runs (the provisioner's env var) and the canonical table
     knows which providers we run. Neither is a question for a human who has not even chosen a language yet.
  2. ONE DEFAULT. `config/profiles.py` said `local` while `voice/engine/core/profile.py` said `remote` — two
     defaults for one concept, in two files, and the disagreement is what made the wizard's answer damaging
     rather than merely redundant. The engine's bare-boot row is now measured AGAINST the table, so a change
     to the table turns this red instead of shipping a voice stack nobody chose.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
MAIN_JS = ROOT / "frontend" / "app" / "main.js"
WIZARD_API = ROOT / "server" / "wizard_api.py"
RESET_SH = ROOT / "scripts" / "reset-memory.sh"


@pytest.fixture(scope="module")
def table() -> dict:
    return json.loads((ROOT / "config" / "models.default.json").read_text(encoding="utf-8"))["services"]


# ── ONE default: the engine's bare boot agrees with the canonical table ───────────────────────────────────

def test_a_bare_boot_uses_the_voice_stack_the_model_table_names(table):
    """`voice/engine/core/profile.py` is what a process with no settings.json gets — every fresh install and
    every factory reset. It shipped voxtral + cartesia while the table said deepgram + elevenlabs, and no
    code path compared the two, so the drift was invisible until somebody read both files on the same day."""
    from voice.engine.core.profile import _DEFAULTS
    remote = _DEFAULTS["remote"]
    assert remote["stt"] == table["stt"]["titular"]["provider"], (
        "the engine's default STT must be the table's titular — this row is what a bare boot uses")
    assert remote["tts"] == table["tts"]["titular"]["provider"], (
        "the engine's default TTS must be the table's titular")


def test_the_config_profile_and_the_engine_profile_no_longer_disagree():
    """The two files name the same concept. `profiles.DEFAULT` must resolve to the package whose
    `engine_profile` is what `voice/engine/core/profile.py` defaults to, or a fresh install boots with one
    file's answer for the voice engine and the other's for the brain."""
    from config import profiles
    from voice.engine.core.profile import PROFILE, _DEFAULTS
    pkg = profiles.get(profiles.DEFAULT)
    assert pkg["engine_profile"] in _DEFAULTS, "the profile names an engine profile that does not exist"
    assert pkg["engine_profile"] == "remote", (
        "the default package must be the canonical cloud-provider stack; `local` is an opt-in, never a default")
    # And the engine's own env fallback agrees when nothing is persisted.
    assert PROFILE in _DEFAULTS
    assert pkg["voice"]["stt_provider"] == _DEFAULTS[pkg["engine_profile"]]["stt"]
    assert pkg["voice"]["tts_provider"] == _DEFAULTS[pkg["engine_profile"]]["tts"]


def test_the_default_profile_brain_is_the_tables_titular(table):
    from config import profiles
    fast = profiles.get(profiles.DEFAULT)["v2"]["fast"]
    assert fast["provider"] == table["voice_brain"]["titular"]["provider"]
    assert fast["model"] == table["voice_brain"]["titular"]["model"]


# ── NOBODY is asked ───────────────────────────────────────────────────────────────────────────────────────

def test_the_profile_question_is_never_asked_in_either_deployment(monkeypatch):
    """A cloud account was already exempt; the question only ever reached a self-hosted human. It is gone for
    both, which is the operator's rule: the process knows where it runs, so it must not ask."""
    from server import wizard_api
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    assert wizard_api._first_run() is False, "self-host must not be asked to pick a profile"
    monkeypatch.setenv("ZAELAR_USER_ID", "usr_real_account")
    assert wizard_api._first_run() is False, "a cloud account must not be asked either"


def test_the_deployment_is_read_and_never_guessed(monkeypatch):
    from config import profiles
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    assert profiles.deployment() == "self_host"
    monkeypatch.setenv("ZAELAR_USER_ID", "usr_real_account")
    assert profiles.deployment() == "cloud"


def test_the_wizard_no_longer_opens_itself_at_boot():
    """The auto-open is what put the question in front of the operator. The panel stays REACHABLE (🧭) —
    what is gone is it deciding for him, unprompted, before he has chosen a language."""
    src = MAIN_JS.read_text(encoding="utf-8")
    code = "\n".join(ln.split("//")[0] for ln in src.splitlines())
    assert "setWizardOpen(true)" not in code, (
        "nothing may auto-open the profile wizard at boot — that is the question the operator removed")
    assert "wizardState()" not in code, "boot must not even ask the wizard whether this is a first run"


# ── the reset cannot reach the installation's configuration ───────────────────────────────────────────────

def test_the_first_run_marker_is_installation_setup_not_agent_identity():
    """This one key is the entire V2-670 defect: on the AGENT side a factory reset dropped it, the wizard
    fired, and it rewrote everything the reset had just been careful to keep."""
    from config import settings as st
    assert "wizard_done" in st.INSTALL_KEYS
    assert "wizard_done" not in st.AGENT_KEYS


def test_a_factory_reset_leaves_the_model_routing_untouched(tmp_path, monkeypatch):
    """The dialog says «nunca se tocan tus claves de API ni el routing de modelos». That is only true if the
    reset preserves the install keys AND nothing downstream reapplies a profile afterwards."""
    from config import settings as st
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({
        "stt_provider": "deepgram", "tts_provider": "elevenlabs",
        "zaelar_profile": "remote", "config_profile": "cloud", "wizard_done": True,
        "stt_language": "es", "assistant_voice": "some-voice", "attention_mode": "smart",
    }), encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    res = st.factory_reset()
    kept = json.loads(f.read_text(encoding="utf-8"))
    assert kept == {"stt_provider": "deepgram", "tts_provider": "elevenlabs",
                    "zaelar_profile": "remote", "config_profile": "cloud", "wizard_done": True}
    assert "stt_language" in res["dropped"], "the language gate must go, or the ceremony never fires"


def test_the_reset_script_never_deletes_the_model_routing_store():
    """`config/v2.json` holds the brain routing. It is in KEEP_ALWAYS and must stay there: the operator's rule
    is that altering the system configuration is not even an OPTION in the reset dialog."""
    src = RESET_SH.read_text(encoding="utf-8")
    keep = src.split("KEEP_ALWAYS=(", 1)[1].split(")", 1)[0]
    assert "config/v2.json" in keep
    body = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    for arr in ("FACTORY_PATHS", "CRED_PATHS", "FACTORY_DIRS_CONTENTS", "FILE_DIRS_CONTENTS"):
        if f"{arr}=(" in body:
            block = body.split(f"{arr}=(", 1)[1].split("\n)", 1)[0]
            assert "config/v2.json" not in block, f"{arr} must never reach the model routing store"
