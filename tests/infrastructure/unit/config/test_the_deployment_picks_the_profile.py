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


# ── V2-725: the SCREEN is gone too, not only its auto-open ────────────────────────────────────────────────
# V2-671 stopped the question firing at boot and left the screen reachable, on the theory that choosing to run
# models on your own machine is a legitimate thing to want. The operator, looking at that screen five days
# later: «esto no tiene sentido, porque cuando se instala el local siempre va a ser local y cuando se instala
# en la nube siempre va a ser en la nube. Así que puedes borrar esta selección y este apartado.» Twice asked is
# a rule, so it is written down here rather than left to the next reader's judgement.

def test_no_route_can_apply_a_profile_from_a_browser():
    """The half that matters more than the screen. `profiles.apply()` writes settings.json AND config/v2.json
    as ONE coordinated lever, so while a POST route existed the engine kept a way to have its model routing
    replaced by a click — which is exactly the damage V2-671 measured. The screen was the only caller; the
    route leaving with it is what makes the fix structural instead of cosmetic."""
    import ast
    tree = ast.parse(WIZARD_API.read_text(encoding="utf-8"))
    # PARSED, not grepped: this module explains the V2-671 defect in its own prose, so a text scan for the
    # lever's name reads the explanation and calls it the crime. A call is a call node.
    routes = [a.args[0].value for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              for a in n.decorator_list
              if isinstance(a, ast.Call) and a.args and isinstance(a.args[0], ast.Constant)]
    assert not [r for r in routes if "profile" in str(r)], (
        f"a route that applies a profile is a route that can rewrite the operator's model routing: {routes}")
    calls = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert "profiles.apply" not in calls, "nothing served over HTTP may fire the coordinated profile lever"


def test_the_setup_panel_never_asks_where_it_is_running():
    """The deployment KNOWS. The panel may still READ the active profile to decide which gaps and which keys
    are worth showing — that is a filter — but it may not offer it, name it, or write it back."""
    wiz = (ROOT / "frontend" / "app" / "components" / "WizardModal.js").read_text(encoding="utf-8")
    code = "\n".join(ln.split("//")[0] for ln in wiz.splitlines())
    for gone in ("renderPerfil", "wizardProfile", "wizard.choose", "wizard.stepPerfilTitle",
                 "wizard.recommended", "wizard.suggestion"):
        assert gone not in code, f"the profile chooser is back in the setup panel: {gone}"
    assert "active_profile" in code, (
        "the panel must still READ the deployment's profile — without it, it offers every gap and every key")


def test_no_word_on_the_setup_panel_offers_a_local_or_cloud_choice():
    """Checked on the STRINGS, in both bundles, because the screen can come back as copy long before it comes
    back as code: a hint that still says «Perfil local» is the same question asked in prose."""
    import json
    for lang in ("es", "en"):
        b = json.loads((ROOT / "i18n" / "bundles" / f"{lang}.json").read_text(encoding="utf-8"))
        offenders = {k: v for k, v in b.items()
                     if (k.startswith("wizard.") or k == "topbar.wizard.title")
                     and ("perfil" in v.lower() or "profile" in v.lower())}
        assert not offenders, f"{lang}: the setup panel still talks about profiles: {offenders}"


def test_settings_is_the_last_icon_before_reset():
    """Operator, same breath: «pon el icono de configuración a la derecha del todo como en todas las
    aplicaciones del mundo… el siguiente icono que aparece a su lado a la izquierda debe ser el de
    configuración». ⚙ used to sit third from the left, which put the one control people reach for by habit in
    the middle of a row of controls they do not. Read by ORDER OF APPEARANCE in the row's source, which is the
    order the DOM gets — the row is one flat h() call with no reordering anywhere."""
    src = (ROOT / "frontend" / "app" / "components" / "TopBar.js").read_text(encoding="utf-8")
    row = src[src.index('h("div", { class: "tr" }'):src.index("ResetConfirm(),")]
    cfg, reset = row.index('id: "cfgBtn"'), row.index('id: "reset"')
    assert cfg < reset, "settings must come before Reset in the row"
    later = [tok for tok in ('id: "statusBtn"', 'id: "debugBtn"', 'id: "daemonBtn"', 'id: "acctBtn"',
                             'id: "memBtn"', 'id: "themeBtn"', 'id: "wizBtn"')
             if tok in row and row.index(tok) > cfg]
    assert not later, f"these icons sit to the RIGHT of settings, and only Reset may: {later}"


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
