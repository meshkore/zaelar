"""«No quiero que la gente hable hasta que no hayamos seleccionado el idioma» (V2-672, 2026-09-11).

The operator, watching his own fresh install: *«me pide los idiomas, pero por detrás está hablando ya en un
idioma por defecto. Eso no es correcto.»* He was describing a WRITTEN DECISION, not a slip —
`voice/engine/pipeline/agent.py` said the question «HAS to go out now, in English (the product default)»
and the kickoff began «[FIRST RUN … SPEAK ENGLISH ONLY]». So the one sentence a person could not understand
was the one asking which language they understand.

And the second half, measured against the live ElevenLabs API on the same day: `SETTINGS.elevenlabs_voice_id`
hardcoded ONE Castilian voice for every language, so English came out with a Spanish accent — his exact
report. The API turns out to answer this properly (`/v1/shared-voices?language=…` returns voices NATIVE to a
language, and honestly returns zero for Swahili), which is what the catalog module is built on.

These tests never touch the network: every catalog read is fed a fake cache.
"""
from __future__ import annotations

import json
import tokenize
from io import StringIO
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
AGENT = ROOT / "voice" / "engine" / "pipeline" / "agent.py"
PICKER_JS = ROOT / "frontend" / "app" / "components" / "LanguageOnboarding.js"


def _code_only(path: Path) -> str:
    """Source with COMMENTS and STRINGS removed. The V2-615 trap: a guard that bans a phrase also bans the
    comment explaining why it is banned, so documenting this decision would turn its own test red."""
    out = []
    for tok in tokenize.generate_tokens(StringIO(path.read_text(encoding="utf-8")).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


# ── the mouth stays shut ──────────────────────────────────────────────────────────────────────────────────

def test_the_first_run_branch_returns_before_it_can_generate_a_reply():
    """Structural, because the branch lives inside a per-session closure with no importable unit (the same
    shape the V2-101 module records). What is asserted is the only thing that matters: on the onboarding
    path control leaves the function before `session.generate_reply` is reachable."""
    src = AGENT.read_text(encoding="utf-8")
    head, _, tail = src.partition("if _onboarding_kickoff:")
    assert tail, "the first-run branch is gone — if it moved, move this guard with it"
    branch, _, rest = tail.partition("\n    else:")
    assert branch.strip().endswith("return"), (
        "the first-run branch must RETURN: nothing may be spoken before a language exists")
    assert "generate_reply" not in branch, "the first-run branch must not generate anything"
    assert "generate_reply" in rest, "the normal kickoff must still greet"


def test_no_utterance_is_composed_in_a_language_nobody_chose():
    """The old kickoff commanded English explicitly. The phrase may survive in the comment that explains why
    it was removed — which is why this reads comment-stripped code."""
    code = _code_only(AGENT)
    assert "SPEAK ENGLISH ONLY" not in code
    assert "FIRST RUN" not in code


# ── the picker ────────────────────────────────────────────────────────────────────────────────────────────

def test_the_catalog_offers_forty_languages_with_a_flag_and_their_own_name():
    from i18n import catalog
    rows = catalog.picker()
    assert len(rows) >= 40, "the operator asked for «los 40 idiomas más populares»"
    assert len({r["code"] for r in rows}) == len(rows), "a duplicated code would render two identical rows"
    for r in rows:
        assert r["flag"].strip(), f"{r['code']} has no flag — the flag IS the label for a non-reader"
        assert r["native"].strip(), f"{r['code']} has no native name"
        assert r["name"].strip()


def test_the_two_shipped_languages_come_first_and_are_marked():
    """«Estarán destacados arriba los dos idiomas que ya tenemos montados y debajo estará el resto.» Those
    two are also the only ones that need no generation, so the claim has to stay true."""
    from i18n import catalog
    from i18n import runtime
    rows = catalog.picker()
    assert [r["code"] for r in rows[:2]] == list(catalog.PINNED)
    assert all(r["pinned"] for r in rows[:2])
    assert not any(r["pinned"] for r in rows[2:])
    assert set(catalog.PINNED) == set(runtime.PRESET), (
        "pinned promises «instant»; it must be exactly what the repo ships")


def test_the_rest_are_ordered_by_the_only_label_on_screen():
    from i18n import catalog
    rest = [r["native"].lower() for r in catalog.picker()[2:]]
    assert rest == sorted(rest), "sorting by our English names produces an order the reader cannot follow"


def test_the_state_endpoint_serves_the_picker(monkeypatch):
    import asyncio
    from server import i18n_api
    state = asyncio.run(i18n_api.i18n_state())
    assert isinstance(state.get("picker"), list) and state["picker"], "the modal has nothing to paint"
    assert "chosen" in state


def test_the_picker_screen_carries_no_sentence_of_ours():
    """The whole point of the redesign. A word in ANY language is a word somebody cannot read; the screen
    speaks in a mark and in flags. (The `title` attribute carries the English name for a screen reader —
    that is assistive metadata, not a label on screen.)"""
    src = PICKER_JS.read_text(encoding="utf-8")
    body = src.split("export function", 1)[1]
    code = "\n".join(ln.split("//")[0] for ln in body.splitlines())
    for prose in ("What language", "would you like", "Say it, or pick", "or type it here"):
        assert prose not in code, f"the picker must not instruct in English: {prose!r}"
    assert "SPEAKING_ICON" in src, "the speaking mark is what tells a non-reader what the screen is for"
    assert "lang-onb-flag" in code and "lang-onb-name" in code


# ── the voice follows the language ────────────────────────────────────────────────────────────────────────

def _fake_catalog(monkeypatch, account, library, lang):
    import time
    from voice.engine.speech import elevenlabs_voices as ev
    monkeypatch.setattr(ev, "_read_cache",
                        lambda: {lang: {"at": time.time(), "account": account, "library": library}})
    monkeypatch.setattr(ev, "_api_key", lambda: "")     # never reach the network from a unit test
    return ev


def test_a_native_voice_outranks_every_multilingual_one(monkeypatch):
    ev = _fake_catalog(
        monkeypatch,
        account=[{"voice": "en1", "label": "Brian", "gender": "m", "lang": "en", "accent": "american"}],
        library=[{"voice": "de1", "label": "Lennard", "gender": "m", "lang": "de", "accent": "standard"}],
        lang="de")
    rows = ev.for_language("de")
    assert rows[0]["voice"] == "de1" and rows[0]["native"] is True
    assert ev.default_voice("de") == "de1"
    assert any(r["voice"] == "en1" for r in rows), (
        "the multilingual fallback is KEPT — a language with no native voice must still be able to speak")


def test_a_language_with_no_native_voice_still_gets_one(monkeypatch):
    """Measured: `shared-voices?language=sw` returns zero. Offering nothing would leave that operator mute."""
    ev = _fake_catalog(
        monkeypatch,
        account=[{"voice": "en1", "label": "Brian", "gender": "m", "lang": "en", "accent": "american"}],
        library=[], lang="sw")
    rows = ev.for_language("sw")
    assert rows and rows[0]["voice"] == "en1"
    assert rows[0]["native"] is False, "it must not CLAIM to be native — it is a fallback and says so"


def test_an_unreachable_api_still_offers_a_real_choice(monkeypatch):
    from voice.engine.speech import elevenlabs_voices as ev
    monkeypatch.setattr(ev, "_read_cache", lambda: {})
    monkeypatch.setattr(ev, "_api_key", lambda: "")
    rows = ev.for_language("en")
    assert len(rows) >= 4 and all(r["source"] == "shipped" for r in rows)


def test_no_castilian_voice_is_hardcoded_for_every_language():
    """The defect, in one line of `core/config.py`. The id may still appear in the comment that records it."""
    cfg = ROOT / "voice" / "engine" / "core" / "config.py"
    code = _code_only(cfg)
    assert "elevenlabs_voice_id" in code, "the env override stays; only its hardcoded value goes"
    src = cfg.read_text(encoding="utf-8")
    line = next(ln for ln in src.splitlines() if ln.strip().startswith("elevenlabs_voice_id"))
    assert 'env("ELEVENLABS_VOICE_ID", "")' in line, f"a default voice is a wrong-language voice: {line}"


def test_the_tts_builder_asks_the_language_before_the_env_fallback():
    src = (ROOT / "voice" / "engine" / "speech" / "tts" / "elevenlabs.py").read_text(encoding="utf-8")
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    i_sel = code.index("selected_voice(")
    i_lang = code.index("elevenlabs_default_voice(")
    i_env = code.index("SETTINGS.elevenlabs_voice_id")
    assert i_sel < i_lang < i_env, (
        "order matters: the operator's own choice, then the language's default, then the env override")


def test_the_language_realignment_covers_every_provider_not_only_kokoro(monkeypatch, tmp_path):
    """This is why the cloud TTS never followed a language change: the realignment named Kokoro."""
    from config import settings as st
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "tts_provider", lambda: "elevenlabs")
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang: f"voice-for-{lang}")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None: False)
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [{"voice": f"voice-for-{lang}"}])
    st.update({"stt_language": "de"})
    assert json.loads(f.read_text(encoding="utf-8"))["assistant_voice"] == "voice-for-de"


def test_a_voice_that_already_suits_the_new_language_is_left_alone(monkeypatch, tmp_path):
    """The counterweight, and the reason `voice_is_aligned` exists as its own question: realigning a voice
    that is ALREADY right for the language would throw away a deliberate choice for nothing."""
    from config import settings as st
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"assistant_voice": "mine"}), encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "tts_provider", lambda: "elevenlabs")
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang: "other")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None: voice == "mine")
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [{"voice": "mine"}, {"voice": "other"}])
    st.update({"stt_language": "de"})
    assert json.loads(f.read_text(encoding="utf-8"))["assistant_voice"] == "mine"


def test_being_in_the_list_is_not_the_same_question_as_being_right_for_the_language(monkeypatch):
    """The trap this whole seam turns on. The ElevenLabs list KEEPS multilingual voices as a fallback, so a
    Castilian voice IS in the English list — a membership check would have found it and changed nothing,
    which is exactly the symptom the operator reported."""
    ev = _fake_catalog(
        monkeypatch,
        account=[{"voice": "es1", "label": "Sara", "gender": "f", "lang": "es", "accent": "peninsular"},
                 {"voice": "en1", "label": "Brian", "gender": "m", "lang": "en", "accent": "american"}],
        library=[], lang="en")
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "elevenlabs_voices", lambda lang=None: ev.for_language("en"))
    assert any(r["voice"] == "es1" for r in ev.for_language("en")), "the fallback must still be offered"
    assert V.voice_is_aligned("elevenlabs", "es1", "en") is False, "a Castilian voice is not right for English"
    assert V.voice_is_aligned("elevenlabs", "en1", "en") is True


def test_a_language_with_no_native_voice_keeps_whatever_is_set(monkeypatch):
    ev = _fake_catalog(
        monkeypatch,
        account=[{"voice": "en1", "label": "Brian", "gender": "m", "lang": "en", "accent": "american"}],
        library=[], lang="sw")
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "elevenlabs_voices", lambda lang=None: ev.for_language("sw"))
    assert V.voice_is_aligned("elevenlabs", "en1", "sw") is True, (
        "with nothing native to offer, swapping one fallback for another only loses a choice")


def test_locking_a_language_persists_it_through_the_ONE_seam_that_moves_the_voice():
    """`lock()` must not grow its own voice alignment. It had one for an afternoon and the dependency ratchet
    (node 7.32) refused it: i18n reaching into the motor's voice catalog. The alignment belongs to
    `settings.update()`, which every language writer already goes through."""
    src = (ROOT / "i18n" / "init" / "detect.py").read_text(encoding="utf-8")
    code = "\n".join(ln.split("#")[0] for ln in src.splitlines())
    assert 'update({"stt_language": code})' in code, "lock must persist through settings.update"
    assert "assistant_voice" not in code, (
        "the voice alignment lives in config/settings.py — a second copy here would drift from the ⚙'s")
    assert "voice.engine.speech" not in code, "i18n must not reach into the motor's voice catalog"
