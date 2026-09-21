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

import asyncio
import json
import os
import tokenize
from io import StringIO
from pathlib import Path

import pytest

from tests.lang import speaking

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
    # V2-745 moved the DECISION to `first_air.silent_first_run()` (with the operator's own words behind it)
    # and left the branch here; the guard follows it, which is what its own message asked for.
    head, _, tail = src.partition("if silent_first_run():")
    assert tail, "the first-run branch is gone — if it moved, move this guard with it"
    branch, _, rest = tail.partition("\n    kickoff_text =")
    assert branch.strip().endswith("return"), (
        "the first-run branch must RETURN: nothing may be spoken before a language exists")
    assert "generate_reply" not in branch, "the first-run branch must not generate anything"
    assert "generate_reply" in rest, "the normal kickoff must still greet"
    # …and the boot veil must come down on that path too, or a first run stares at the splash for ever
    # while the picker it is supposed to be using sits underneath it (V2-745).
    assert "_air.lift()" in branch, "a silent first run must lift the veil: nothing is going to sound"


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


def test_the_shipped_languages_come_first_as_their_REGIONAL_VARIANTS():
    """«Estarán destacados arriba los dos idiomas que ya tenemos montados y debajo estará el resto» —
    and, since V2-734, each of those two is offered as the regional variants a listener tells apart:
    *«no es lo mismo el español de España que el español latino… eso nos ayudará a elegir por defecto la
    voz más adecuada»*. The variants are the same language underneath, which is what `base` says.
    """
    from i18n import catalog
    from i18n import runtime
    rows = catalog.picker()
    head = [r for r in rows if r["pinned"]]
    assert [r["code"] for r in head] == ["en-US", "en-GB", "es-ES", "es-419"], [r["code"] for r in head]
    assert rows[:len(head)] == head, "the shipped ones come FIRST, not merely marked"
    assert {r["base"] for r in head} == set(catalog.PINNED), (
        "a variant is not a new language: its base is what the bundle and the STT use")
    assert set(catalog.PINNED) == set(runtime.PRESET), (
        "pinned promises «instant»; it must be exactly what the repo ships")
    assert all(r["region"] for r in head), "and each one says WHICH region, or it cannot pick a voice"


def test_the_rest_are_ordered_by_the_only_label_on_screen():
    from i18n import catalog
    rows = catalog.picker()
    rest = [r["native"].lower() for r in rows if not r["pinned"]]
    assert rest == sorted(rest), "sorting by our English names produces an order the reader cannot follow"
    assert not any(r["region"] for r in rows if not r["pinned"]), (
        "only a language we SHIP is split by region — the rest have one voice to offer at best")


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
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang, region="": f"voice-for-{lang}")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None, region=None: False)
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [{"voice": f"voice-for-{lang}"}])
    # `settings.update()` writes ZAELAR_LANGUAGE into the PROCESS env — correct in production (the store
    # overrides the env) and a suite-wide leak here: without this, every test after these two measured a
    # German engine. `speaking()` puts it back. Caught by V2-684's leak guard.
    with speaking("en"):
        st.update({"stt_language": "de"})
        assert json.loads(f.read_text(encoding="utf-8"))["assistant_voice"] == "voice-for-de"


# ── the region decides the accent (V2-734) ────────────────────────────────────────────────────────────────

_ES_ACCOUNT = [
    {"voice": "elena", "label": "Elena", "gender": "f", "lang": "es", "accent": "peruvian"},
    {"voice": "sara",  "label": "Sara",  "gender": "f", "lang": "es", "accent": "peninsular"},
]
_ES_LIBRARY = [
    {"voice": "brian", "label": "Brian", "gender": "m", "lang": "es", "accent": "latin american"},
]


def test_spain_and_latin_america_are_not_the_same_voice(monkeypatch):
    """The operator, hearing his Castilian read by a Peruvian voice (2026-09-20): *«no es lo mismo el
    español de España que el español latino… pon inglés de Estados Unidos, inglés de Reino Unido, español
    de España o español latino. Eso nos ayudará a elegir por defecto la voz más adecuada»*.

    This is his own account, in miniature: `Elena (peruvian)` happens to be first, so «the first native
    voice» — correct until now — handed Peruvian Spanish to a Castilian operator while `Sara (peninsular)`
    sat one row below.
    """
    ev = _fake_catalog(monkeypatch, account=_ES_ACCOUNT, library=_ES_LIBRARY, lang="es")
    assert ev.default_voice("es", "ES") == "sara", "«español de España» is the peninsular one"
    assert ev.default_voice("es", "419") == "brian", "«español latino» is not"
    assert ev.default_voice("es") == "elena", (
        "with no region stated, nothing changes — the rule is a preference, not a new default")


def test_a_region_whose_accent_nobody_has_falls_back_instead_of_choosing_wrong(monkeypatch):
    """A region is a preference over what EXISTS. Inventing a match would be worse than not having one."""
    ev = _fake_catalog(
        monkeypatch,
        account=[{"voice": "de1", "label": "Lennard", "gender": "m", "lang": "de", "accent": "standard"}],
        library=[], lang="de")
    assert ev.default_voice("de", "ES") == "de1", "no peninsular German exists; the native one still wins"
    assert ev.accents_for("ZZ") == (), "a region we do not split has no opinion"


def test_switching_region_realigns_even_though_BOTH_voices_are_native(monkeypatch):
    """The trap one level in, and the same shape as the one `voice_is_aligned` was built for.

    A Castilian voice IS a native Spanish voice, so «is it native» answers yes for an operator who has
    just switched to «español latino» — and the switch would change nothing, which is exactly the symptom
    that started all of this.
    """
    _fake_catalog(monkeypatch, account=_ES_ACCOUNT, library=_ES_LIBRARY, lang="es")
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "picked_region", lambda: "")
    assert V.voice_is_aligned("elevenlabs", "sara", "es", "ES") is True
    assert V.voice_is_aligned("elevenlabs", "sara", "es", "419") is False, (
        "THE TRAP: native is not the same question as native TO THIS REGION")
    assert V.voice_is_aligned("elevenlabs", "sara", "es", "") is True, (
        "and with no region chosen the operator's voice is left exactly where it is")


def test_a_regional_code_never_reaches_the_language_itself(monkeypatch, tmp_path):
    """`stt_language` and `ZAELAR_LANGUAGE` have always been a bare language code and every reader
    downstream depends on that. The region is persisted BESIDE it, by the one door both callers use."""
    from config import settings as st
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "tts_provider", lambda: "elevenlabs")
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang, region="": f"voice-{lang}-{region}")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None, region=None: False)
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [])
    with speaking("en"):
        st.update({"stt_language": "es-419"})
        saved = json.loads(f.read_text(encoding="utf-8"))
        assert saved["stt_language"] == "es", f"the language is bare: {saved['stt_language']!r}"
        assert saved["language_region"] == "419", saved
        assert os.environ["ZAELAR_LANGUAGE"] == "es", (
            "the env the whole engine reads must never carry a region")
        assert saved["assistant_voice"] == "voice-es-419", (
            "and the realignment has to ASK with the region, or the variants decide nothing")


def test_the_lock_accepts_a_regional_code_and_works_on_the_language(monkeypatch):
    """`lock("es-419")` prepares Spanish, not a language called «es-419» — and hands the FULL code to the
    one door that knows how to split it."""
    from i18n.init import detect
    calls = []
    monkeypatch.setattr(detect, "_pending_steps", lambda code: calls.append({"pending": code}) or [])
    from config import settings as _st
    monkeypatch.setattr(_st, "update", lambda payload: calls.append(dict(payload)) or {"applied": []})
    from memory import api as _mem
    monkeypatch.setattr(_mem, "set_state", lambda d: None)
    from i18n import init as init_pkg

    async def _prep(code):
        calls.append({"prepare": code})
        return {}
    monkeypatch.setattr(init_pkg, "prepare", _prep)
    from i18n import runtime as rt
    monkeypatch.setattr(rt, "strings", lambda code: {})
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: None)

    with speaking("en"):
        res = asyncio.run(detect.lock("es-419", onboarding=False))
    assert res["ok"] is True and res["code"] == "es", res
    assert {"stt_language": "es-419"} in calls, f"the FULL code goes to the door that splits it: {calls}"
    assert {"prepare": "es"} in calls, f"and everything else works on the language: {calls}"
    assert {"pending": "es"} in calls


def test_a_code_that_is_not_a_language_is_refused(monkeypatch):
    """And a trailing dash is not a region — it normalises to the plain language rather than being
    treated as one, because «es-» is a typo, not a request for an accent."""
    from i18n.init import detect
    from i18n.catalog import split_locale
    monkeypatch.setattr(detect, "_pending_steps", lambda code: [])
    from config import settings as _st
    monkeypatch.setattr(_st, "update", lambda payload: {"applied": []})
    from memory import api as _mem
    monkeypatch.setattr(_mem, "set_state", lambda d: None)
    from voice import observer
    monkeypatch.setattr(observer, "emit", lambda *a, **kw: None)

    assert split_locale("es-") == ("es", "")
    with speaking("en"):
        for bad in ("-ES", "e", "es-TOOLONG", "123", ""):
            res = asyncio.run(detect.lock(bad, onboarding=False))
            assert res["ok"] is False, f"{bad!r} must not lock anything"


class _FakeTTS:
    """A plugin that CAN be re-pointed, shaped like the installed ElevenLabs one (measured 2026-09-20:
    `update_options(*, voice_id, voice_settings, model, language, …)`)."""

    def __init__(self):
        self.calls = []

    def update_options(self, *, voice_id=None, language=None):
        self.calls.append({"voice_id": voice_id, "language": language})


def test_the_realigned_voice_reaches_the_session_that_is_ALREADY_SPEAKING(monkeypatch, tmp_path):
    """V2-733 — the operator, arriving in Spanish on a fresh install: «me sale la voz del señor inglés
    intentando hablar español, con lo cual lo hace muy mal».

    Everything above this line already worked: the language locks, the voice realigns, the right id lands
    in settings.json. What did not exist is the last metre. The TTS is constructed when the pipeline is
    built and reads its voice once, so the correct voice sat on disk waiting for a reconnect that
    onboarding never asks for — and the session went on speaking the new language in the old language's
    voice, starting with `onboarding.confirmSpoken`, which IS the first sentence he ever hears.
    """
    from config import settings as st
    from voice.engine.speech import live_tts
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "tts_provider", lambda: "elevenlabs")
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang, region="": f"voice-for-{lang}")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None, region=None: False)
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [{"voice": f"voice-for-{lang}"}])

    fake = _FakeTTS()
    live_tts.attach(fake, "elevenlabs")
    try:
        with speaking("en"):
            res = st.update({"stt_language": "de"})
    finally:
        live_tts.detach(fake)

    assert json.loads(f.read_text(encoding="utf-8"))["assistant_voice"] == "voice-for-de"
    assert fake.calls == [{"voice_id": "voice-for-de", "language": "de"}], (
        f"THE BUG: the live session never heard about the new voice — {fake.calls}")
    assert "assistant_voice(en vivo)" in res["applied"], (
        "and the save has to SAY it went live, or nobody can tell this from the old behaviour")


def test_the_language_lock_is_locked_too_not_only_the_voice(monkeypatch, tmp_path):
    """A multilingual model drifts in accent on short text when it is not told which language it is
    speaking (V2-035). Re-pointing the voice without the language would fix half the complaint."""
    from config import settings as st
    from voice.engine.speech import live_tts
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "tts_provider", lambda: "elevenlabs")
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang, region="": "v")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None, region=None: False)
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [{"voice": "v"}])
    fake = _FakeTTS()
    live_tts.attach(fake, "elevenlabs")
    try:
        with speaking("en"):
            st.update({"stt_language": "es"})
    finally:
        live_tts.detach(fake)
    assert fake.calls and fake.calls[0]["language"] == "es", fake.calls


def test_with_no_session_speaking_the_save_is_exactly_what_it_always_was(monkeypatch, tmp_path):
    """Nothing about this may depend on a session existing: the ⚙ is used with the voice off, and the
    cloud provisions a Machine before anybody connects to it."""
    from config import settings as st
    from voice.engine.speech import live_tts
    live_tts.detach()
    f = tmp_path / "settings.json"
    f.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "tts_provider", lambda: "elevenlabs")
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang, region="": "v")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None, region=None: False)
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [{"voice": "v"}])
    with speaking("en"):
        res = st.update({"stt_language": "es"})
    assert json.loads(f.read_text(encoding="utf-8"))["assistant_voice"] == "v"
    assert "assistant_voice(en vivo)" not in res["applied"], "and it must not CLAIM it went live"


def test_a_plugin_that_cannot_be_repointed_degrades_instead_of_raising():
    """Every failure here ends as «it applies on the next connect», never as an exception: a voice that
    could not be swapped must not take down the settings save that was otherwise fine."""
    from voice.engine.speech import live_tts

    class _Deaf:                      # no update_options at all
        pass

    class _Strange:                   # has one, but names the voice something else entirely
        def update_options(self, *, timbre=None):
            raise AssertionError("must not be called with a voice it cannot take")

    class _Angry:
        def update_options(self, *, voice_id=None, language=None):
            raise RuntimeError("the socket is gone")

    for obj in (_Deaf(), _Strange(), _Angry()):
        live_tts.attach(obj, "elevenlabs")
        try:
            assert live_tts.apply_voice("v", "es") is False, f"{type(obj).__name__} must report failure"
        finally:
            live_tts.detach(obj)
    assert live_tts.apply_voice("v", "es") is False, "and with nothing attached there is nothing to do"


def test_the_pipeline_hands_over_the_tts_it_just_built():
    """The seam is worthless if nobody registers the live TTS, and that call lives in the one place that
    has it: right where `entrypoint()` acquires it, before the session is constructed."""
    src = (ROOT / "voice" / "engine" / "pipeline" / "agent.py").read_text(encoding="utf-8")
    i_build = src.index('tts = ctx.proc.userdata.get("tts") or build_tts()')
    i_attach = src.index("live_tts.attach(tts,", i_build)
    i_session = src.index("session = AgentSession(", i_build)
    assert i_build < i_attach < i_session, "attach between building the TTS and building the session"


def test_a_voice_that_already_suits_the_new_language_is_left_alone(monkeypatch, tmp_path):
    """The counterweight, and the reason `voice_is_aligned` exists as its own question: realigning a voice
    that is ALREADY right for the language would throw away a deliberate choice for nothing."""
    from config import settings as st
    f = tmp_path / "settings.json"
    f.write_text(json.dumps({"assistant_voice": "mine"}), encoding="utf-8")
    monkeypatch.setattr(st, "SETTINGS_FILE", f)
    from voice.engine.speech import voices as V
    monkeypatch.setattr(V, "tts_provider", lambda: "elevenlabs")
    monkeypatch.setattr(V, "default_voice_for", lambda prov, lang, region="": "other")
    monkeypatch.setattr(V, "voice_is_aligned", lambda prov, voice, lang=None, region=None: voice == "mine")
    monkeypatch.setattr(V, "voices_for", lambda prov, lang=None: [{"voice": "mine"}, {"voice": "other"}])
    with speaking("en"):
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


def test_the_settings_panel_offers_the_SAME_languages_as_the_first_run_picker():
    """Two answers to one question is how they disagree. Onboarding could lock a language the ⚙ then could
    not switch back to, because `langs.supported()` only lists the ones with a verified native Kokoro voice
    — the right rule for that module, the wrong list for this dropdown."""
    from config import settings as st
    from i18n import catalog
    knob = next(k for k in st.effective()["knobs"] if k["key"] == "stt_language")
    assert [o["value"] for o in knob["options"]] == [r["code"] for r in catalog.picker()]
    assert all(o["label"].strip() for o in knob["options"])


def test_the_language_dropdown_never_renders_empty(monkeypatch):
    """A settings panel with no languages at all is worse than one with the two we ship."""
    from config import settings as st
    from i18n import catalog
    monkeypatch.setattr(catalog, "picker", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    rows = st._ui_languages()
    assert [r["code"] for r in rows] == ["en", "es"]
