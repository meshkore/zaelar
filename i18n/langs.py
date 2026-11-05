"""The languages the agent SPEAKS — one `LangSpec` per language, built from its genesis packs.

Every word lives in `i18n/genesis/<code>/voice.json` (+ `smalltalk.json`) for the languages the repo ships, and in
`<workspace>/i18n/generated/<code>/` for any other the operator onboarded (`i18n.packs`). This module only joins
those words to the few TECHNICAL facts of a language (its Kokoro voices, its lang codes) and answers «what is the
active language». A language with no verified native Kokoro voice still gets its whole spoken table — the cloud
TTS speaks it — and borrows English's local voices, which is the only part it cannot have.

Live, not frozen: ``current_language()`` reads ``ZAELAR_LANGUAGE`` from the environment (the ⚙ and onboarding
write it), so a language change applies on the next voice session.
"""
from __future__ import annotations

import os
from i18n.langspec import (  # noqa: E402,F401 — V2-778 F1: moved, imported back under their names
    LangSpec)
from i18n import packs as _packs

# The TECHNICAL half of a language: what no translator produces. Kokoro voices are language-specific and only
# verified-native ones are listed, so a voice can never be sent through the wrong-language pipeline.
_TECH: dict[str, dict] = {
    "es": {"name": "Spanish", "native": "Español", "kokoro_lang": "e", "kokoro_default": "ef_dora",
           "kokoro_voices": [{"label": "Dora (es, f)", "voice": "ef_dora", "gender": "f"},
                             {"label": "Alex (es, m)", "voice": "em_alex", "gender": "m"},
                             {"label": "Santa (es, m)", "voice": "em_santa", "gender": "m"}]},
    "en": {"name": "English", "native": "English", "kokoro_lang": "a", "kokoro_default": "af_bella",
           "kokoro_voices": [{"label": "Bella (en, f)", "voice": "af_bella", "gender": "f"},
                             {"label": "Nicole (en, f)", "voice": "af_nicole", "gender": "f"},
                             {"label": "Michael (en, m)", "voice": "am_michael", "gender": "m"},
                             {"label": "Adam (en, m)", "voice": "am_adam", "gender": "m"}]},
}


def _tuples(v):
    """JSON lists back to the tuples the dataclass declares (lists of lists too); dicts keep their shape."""
    if isinstance(v, list):
        return tuple(_tuples(x) for x in v)
    if isinstance(v, dict):
        return {k: _tuples(x) for k, x in v.items()}
    return v


_FIELDS: frozenset[str] = frozenset()


def _build(code: str) -> LangSpec:
    global _FIELDS
    if not _FIELDS:
        from dataclasses import fields as _dc_fields
        _FIELDS = frozenset(f.name for f in _dc_fields(LangSpec))
    voice = {k: v for k, v in _packs.read("voice", code).items() if k in _FIELDS}
    if isinstance(voice.get("form_fact_names"), dict):
        voice["form_fact_names"] = tuple(voice["form_fact_names"].items())
    tech = dict(_TECH.get(code) or _TECH[_packs.BASE])
    if code not in _TECH:
        try:
            from i18n import catalog as _cat
            lang = _cat.get(code)
            tech.update(name=lang.name, native=lang.native) if lang else None
        except Exception:  # noqa: BLE001 — a name for logs is not worth failing a language over
            tech.update(name=code, native=code)
    book = {k: v for k, v in (_packs.read("smalltalk", code) or {}).items() if not k.startswith("_")}
    return LangSpec(code=code, smalltalk=_tuples(book), **tech, **{k: _tuples(v) for k, v in voice.items()})


LANGUAGES: dict[str, LangSpec] = {c: _build(c) for c in _packs.PRESET}
_GENERATED: dict[str, LangSpec] = {}


_WORDS: dict[str, dict] = {}


def invalidate() -> None:
    """Forget the built generated languages (a pack was just generated or topped up)."""
    _GENERATED.clear()
    _WORDS.clear()


def words(path: str, code: str | None = None, default=None):
    """One entry of the `voice` pack that is not a LangSpec field — a module's own spoken lines or word lists,
    grouped by module («agenda.week_labels», «music.not_found»). Lists come back as tuples. The active language
    (or `code`), then English, then `default`: a third language never inherits Spanish by accident.

    This is the door for every table that used to be `{"es": …, "en": …}` inside a module."""
    c = (code or current_code() or DEFAULT_LANG).strip().lower()
    for lang in (c, _packs.BASE):
        tree = _WORDS.get(lang)
        if tree is None:
            tree = _WORDS[lang] = _packs.read("voice", lang) or {}
        node = tree
        for part in str(path).split("."):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if node not in (None, "", [], {}):
            return _tuples(node)
    return default


def _known(code: str) -> bool:
    """A language we can run: shipped, or one the operator onboarded (anything generated on disk)."""
    return code in LANGUAGES or bool(_packs.generated("voice", code) or _packs.generated("ui", code))

# The product DEFAULT is ENGLISH (operator policy 2026-08-09; it used to be Spanish). A newly
# installed zaelar with no language selected starts in English — like the frontend (`store.lang()` already fell back to "en") and
# the i18n manifest. A clean installation therefore no longer has an English UI and Spanish VOICE.
# This does NOT mean "zaelar speaks English": it is only the starting point until AUTODETECTION of the first phrase
# sets the operator's actual language (`i18n/init/detect.py`) or until they choose it in ⚙. No existing installation
# changes: once `stt_language` is persisted, this value is not consulted.
DEFAULT_LANG = "en"


def _default_code() -> str:
    """The fallback when `ZAELAR_LANGUAGE` names no language this build ships.

    V2-676 — it used to read `voice.engine.core.config.SETTINGS.language`, which is itself
    `env("ZAELAR_LANGUAGE", "en")` frozen at that module's import. Reading the variable directly is exactly
    equivalent (its only caller, `current_code()`, has already checked the live value against the catalog and
    only lands here when it does not match) and it is what lets this table live OUTSIDE the voice motor,
    which every consumer was reaching into just to say one sentence."""
    code = (os.getenv("ZAELAR_LANGUAGE") or "").strip().lower()
    return code if code and _known(code) else DEFAULT_LANG


def first_run_auto() -> bool:
    """Are we still on the first run, with NO language selected yet? Then STT must transcribe in AUTO instead
    of fixing a language: it is the only way for an Arabic- or Chinese-speaking operator to be transcribed CORRECTLY in their
    first phrase — and that clean text is exactly what `i18n.init.detect` classifies to set the language.

    It lives HERE (one answer for all three STT backends) because otherwise each adapter invents its own:
    `whisper_local` already did this on its own while the REMOTE backends (deepgram/voxtral) did not — meaning that in the cloud
    profile, which is the production one, autodetection started with STT pinned to the default language and could not
    work. Defensive by design (fail-closed): if i18n is unavailable, it behaves as before.

    Each backend translates this into ITS way of saying «auto» — there is no common token: Whisper wants `language=None`,
    Voxtral wants the parameter OMITTED, and Deepgram needs explicit `"multi"` (omitting it falls back to en-US on the
    server, which is NOT auto)."""
    try:
        from i18n.init import detect as _detect
        return bool(_detect.should_detect())
    except Exception:
        return False


def current_code() -> str:
    """The ACTIVE language code, read LIVE from the env (⚙ writes ZAELAR_LANGUAGE),
    validated against the catalog so an unsupported value can't break alignment."""
    env = (os.getenv("ZAELAR_LANGUAGE") or "").strip().lower()
    if env and _known(env):
        return env
    return _default_code()


def _spec_of(code: str) -> LangSpec:
    if code in LANGUAGES:
        return LANGUAGES[code]
    hit = _GENERATED.get(code)
    if hit is None:
        hit = _GENERATED[code] = _build(code)
    return hit


def current_language() -> LangSpec:
    return _spec_of(current_code())


def spec(code: str | None = None) -> LangSpec:
    c = (code or "").strip().lower()
    if c and _known(c):
        return _spec_of(c)
    return current_language()


def supported() -> list[LangSpec]:
    """Catalog for the ⚙ UI, with Spanish first."""
    return [LANGUAGES[c] for c in sorted(LANGUAGES, key=lambda c: (c != DEFAULT_LANG, c))]


def kokoro_voices(code: str | None = None) -> list[dict]:
    return spec(code).kokoro_voices


import random as _random  # noqa: E402


def smalltalk_book(code: str | None = None) -> dict:
    """The PHRASEBOOK for a language (V2-674): the hardcoded es/en table, with a GENERATED pack layered on top.

    Same lookup order as `pick_filler`: whatever the generated `smalltalk` pack holds WINS, because a
    pack generated for that language is native and this table is not. The merge is per INTENT — a pack that
    only translated greetings still gets the rest — and a language with neither answers `{}`, which the lane
    reads as «not my business» and hands the turn to the model. Failing into the model is the right fallback:
    a wrong canned greeting is worse than a slow correct answer."""
    c = (code or current_code()).lower()
    # `spec()` answers with the ACTIVE language for anything it does not know, which is right for a filler
    # pool and wrong here: it would hand a German operator the English phrasebook, and the one intent that
    # could still match («hello») would be answered in English, deterministically and with no model to
    # correct it. An unknown language has no book until one is generated for it.
    base = dict(LANGUAGES[c].smalltalk or {}) if c in LANGUAGES else {}
    gen = {} if c in LANGUAGES else _tuples(_packs.generated("smalltalk", c) or {})
    if not gen:
        return base
    out = {"vocatives": tuple(gen.get("vocatives") or base.get("vocatives") or ()),
           "joiners": tuple(gen.get("joiners") or base.get("joiners") or ())}
    intents = dict(base.get("intents") or {})
    for name, spec_in in (gen.get("intents") or {}).items():
        if not isinstance(spec_in, dict):
            continue
        merged = dict(intents.get(name) or {})
        merged.update({k: v for k, v in spec_in.items() if v})
        intents[name] = merged
    out["intents"] = intents
    return out


_RECENT_FILLERS: list[str] = []   # V2-640: the anti-repetition remembers a few turns back, not one —
_RECENT_MAX = 4                   # the operator heard «A ver…» twice in three turns with depth-1 memory.


def pick_filler(last: str = "", code: str | None = None, kind: str = "neutral") -> str:
    """A varied lead-in in the active language, MATCHED to the turn's shape and not heard recently.
    Shapes (V2-572 + V2-640): `kind="action"` draws from the action pool («Voy…») — a thinking sound before
    an order to act reads as incomprehension; `kind="social"` draws from the explanation-openers («Pues…») —
    a thinking sound answering a question about the conversation itself is what turned the 19:27 session
    into a dialogue of besugos; `kind="ack"` draws from the receipt pool («Vale…») — the turn ANSWERS a
    question we just asked, so nothing is being looked up and nothing is being explained (V2-716); anything
    else keeps the thinking pool. Anti-repetition is a small RECENT window (depth {n}), not just the last
    phrase. Deterministic-agnostic: no pool → empty string → the caller says nothing.""".format(n=_RECENT_MAX)
    if kind == "action":
        pool = list(getattr(spec(code), "fillers_action", ()) or ())
    elif kind == "social":
        pool = list(getattr(spec(code), "fillers_social", ()) or ())
    elif kind == "ack":
        pool = list(getattr(spec(code), "fillers_ack", ()) or ())
    else:
        pool = list(getattr(spec(code), "fillers", ()) or ())
    if not pool:
        return ""
    avoid = set(_RECENT_FILLERS[-_RECENT_MAX:]) | ({last} if last else set())
    choices = [p for p in pool if p not in avoid] or [p for p in pool if p != last] or pool
    phrase = _random.choice(choices)
    _RECENT_FILLERS.append(phrase)
    del _RECENT_FILLERS[:-8]
    return phrase


_RECENT_COVERS: list[str] = []


def pick_cover(kind: str, target: str = "", last: str = "", code: str | None = None) -> str:
    """The WORK COVER for the tool seam (V2-669): a short line that names WHERE we are about to look, chosen
    once the router has already decided. `kind` is "widget" | "search" | "recall"; `target` fills `{t}` for the
    widget pool (the card's own title). Varied against a recent window like `pick_filler`, and — crucially —
    against the LEAD-IN that may have just sounded (`last`), because the one thing this must never be is the
    same wait said twice. No pool, or an unknown kind, returns "" and the caller stays silent."""
    field = {"widget": "covers_widget", "search": "covers_search", "recall": "covers_recall"}.get(kind or "")
    if not field:
        return ""
    pool = list(getattr(spec(code), field, ()) or ())
    if not pool:
        return ""
    avoid = set(_RECENT_COVERS[-_RECENT_MAX:]) | ({last} if last else set())
    # Three rungs like `pick_filler`, and the MIDDLE one is the point: once the recent window has swallowed a
    # short pool, falling straight back to it would hand back the very phrase we must not repeat.
    choices = [p for p in pool if p not in avoid] or [p for p in pool if p != last] or pool
    phrase = _random.choice(choices)
    _RECENT_COVERS.append(phrase)
    del _RECENT_COVERS[:-8]
    if "{t}" in phrase:
        t = (target or "").strip()
        if not t:
            return ""                      # a widget cover with nothing to name says less than silence
        phrase = phrase.replace("{t}", t)
    return phrase


def pick_ack(last: str = "", code: str | None = None) -> str:
    """The spoken «done» after an EXECUTED direct action (the action-map fast lane, V2-572). Varied like the
    fillers and never the same twice in a row; empty string when the language ships no pool."""
    pool = list(getattr(spec(code), "acks", ()) or ())
    if not pool:
        return ""
    choices = [p for p in pool if p != last] or pool
    return _random.choice(choices)


__all__ = ["LangSpec", "LANGUAGES", "DEFAULT_LANG", "current_code", "current_language",
           "spec", "supported", "kokoro_voices", "pick_filler", "pick_cover", "pick_ack"]
