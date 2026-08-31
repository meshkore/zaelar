"""
i18n.init.detect — first-run language auto-detection (V2-089 P3).

"We're an AI; we should figure it out." On a brand-new install (the operator hasn't picked a language yet) we
detect the language from their FIRST utterances and lock it — no trip to settings. INITIALIZATION, not the hot
path: it runs a couple of times at the very start, then never again.

Gate: should_detect() is True only until a language is explicitly set (persisted `stt_language` in settings.json
— written either by this lock() or by a manual ⚙ change). So auto-detection NEVER overrides a deliberate choice.

Detection: a Unicode-script heuristic catches non-Latin languages instantly (Arabic, CJK, Cyrillic, …); anything
Latin-script (es/en/fr/…) goes to a cheap constrained LLM classify. Works off whatever the first-run STT (running
in auto mode) transcribed.

Lock: persist ZAELAR_LANGUAGE, prepare() the UI bundle (generate if the language is new), and emit an SSE
`language` event so the frontend flips the whole UI live.
"""
from __future__ import annotations

import json
import re

from loguru import logger

# Unicode-script → ISO-639-1. Order matters: check kana (ja) before bare Han (zh).
_SCRIPT = [
    ("ja", r"[぀-ヿ]"),                 # hiragana/katakana
    ("ko", r"[가-힯]"),                 # hangul
    ("zh", r"[一-鿿]"),                 # han (after kana → zh)
    ("ar", r"[؀-ۿ]"),                 # arabic
    ("he", r"[֐-׿]"),                 # hebrew
    ("ru", r"[Ѐ-ӿ]"),                 # cyrillic
    ("el", r"[Ͱ-Ͽ]"),                 # greek
    ("hi", r"[ऀ-ॿ]"),                 # devanagari
    ("th", r"[฀-๿]"),                 # thai
]

_should_cache: bool | None = None


def should_detect() -> bool:
    """True on a fresh install where no language has been chosen yet. Cached (invalidated on lock)."""
    global _should_cache
    if _should_cache is not None:
        return _should_cache
    persisted = {}
    try:
        from config.settings import SETTINGS_FILE
        persisted = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        persisted = {}
    _should_cache = not str(persisted.get("stt_language") or "").strip()
    return _should_cache


def _by_script(text: str) -> str | None:
    for code, pat in _SCRIPT:
        if re.search(pat, text):
            return code
    return None


_BARE_CODE = re.compile(r"^[a-z]{2}$")
_WORD_CODE = re.compile(r"\b[a-z]{2}\b")


def extract_code(raw: str | None) -> str | None:
    """The ISO-639-1 code the classifier MEANT, or None when the reply does not unambiguously carry one.

    The old parse was `re.search(r"[a-z]{2}", raw.lower())` — the first two lowercase letters ANYWHERE. That
    reads a preamble as the answer, and every wrong answer it produces is itself a valid ISO code, so nothing
    downstream can tell. Measured 2026-08-21:

        "It is Spanish (es)"   -> 'it'  (Italian)     "The language is es." -> 'th'  (Thai)
        "Language: es"         -> 'la'  (Latin)       "Sure, es"            -> 'su'  (Sundanese)

    It then gets PERSISTED as the operator's deliberate choice, `should_detect()` goes False, and the run never
    retries. The cost is not cosmetic: the same code resolves `nucleo/flash/site_catalog.py`'s locale, so the
    errand goes to the wrong country's sites on turn 1 — the exact failure this module blocks the turn to avoid.

    Seen live once in 66 saved rounds (2026-08-21 02:39), and the harness recorded it: the classifier only answers
    with a SENTENCE when the model is degraded or relaying. So the rule is «unambiguous or nothing»:

      1. the cleaned reply IS a code -> take it (the healthy path, 65 of those 66 rounds);
      2. otherwise, whole-word two-letter tokens, and accept ONLY if there is exactly one — "Language: es" has
         one, "It is Spanish (es)" has three (it/is/es) and is refused;
      3. anything else -> None.

    Refusing is the safe side and not a dead end: nothing is persisted, `should_detect()` stays True, and the
    next utterance tries again. A wrong lock is silent and permanent; a refused one costs a retry.

    Validating against a list of ISO codes would NOT have caught any of this — `it`, `th`, `la` and `su` are all
    real codes. The defect is in the EXTRACTION, so that is where the fix goes.
    """
    text = (raw or "").strip().lower()
    if not text:
        return None
    cleaned = text.strip("\"'`.,:;!?()[]{} \t\n")
    if _BARE_CODE.match(cleaned):
        return cleaned
    found = list(dict.fromkeys(_WORD_CODE.findall(text)))
    return found[0] if len(found) == 1 else None


def _by_llm(text: str) -> str | None:
    """Constrained classify: return the ISO-639-1 code of the text, nothing else. Fail-open → None."""
    try:
        from nucleo import memllm
        raw = memllm.chat_sync(
            "i18n",
            "Identify the language of the user's text. Reply with ONLY its ISO 639-1 two-letter code "
            "(lowercase, e.g. 'en', 'es', 'fr', 'de', 'pt'). No other text.",
            # 16, not 4 (2026-08-21). The cap is what turned this from a refusable answer into an accepted
            # WRONG one: a classifier that replies with a sentence gets cut to its first word, and "It is
            # Spanish" becomes "It" — which `extract_code` accepts, because `it` IS Italian's code. Seen live
            # at 10:12 with the fix already in the tree: the sandbox persisted `stt_language: "it"` on a Spanish
            # run. Uncut, the same reply arrives as "It is Spanish (es)" — three two-letter words, ambiguous,
            # refused. The ceiling costs a handful of tokens on ONE call at first run.
            text[:500], max_tokens=16, temperature=0.0, timeout=20.0)
        code = extract_code(raw)
        if code is None and (raw or "").strip():
            # What the model actually SAID, once, when we refuse it. Without this the only evidence of a bad
            # detection is the locked code itself, which is indistinguishable from a correct one — answering
            # "was it the parse or the model?" took a measurement instead of a grep.
            logger.info("i18n.detect: reply not an unambiguous code, not locking: %r", (raw or "")[:120])
        return code
    except Exception:
        return None


def classify(text: str) -> str | None:
    """Best-effort language code for a transcript. Script heuristic first (instant, non-Latin), else LLM."""
    text = (text or "").strip()
    if len(text) < 2:
        return None
    return _by_script(text) or _by_llm(text)


def ensure_for_text(text: str) -> str | None:
    """First-run detection for a TEXT-only channel: classify `text` and lock the language, synchronously.

    The voice pipeline has its own path (`voice/engine/pipeline/agent.py`), and a much better one: it ASKS,
    behind a blocking modal, and locks what the operator answers. A text channel has no modal and no turn to
    spare on the question, so it falls back to what V2-089 did before V2-101 added the modal — a silent guess
    off the first utterance. Deliberately NOT called from the voice provider: locking a language there would
    race the onboarding question and could commit the wrong one before the operator has answered it.

    Why it blocks instead of running in the background: the language is not only how the reply reads, it is
    what `nucleo/flash/site_catalog.py` resolves its locale from. Measured 2026-08-20 on a fresh engine — the
    state every sandbox run and every new install starts in — the SAME Spanish errand is handed
    `www.opentable.com`, `www.ticketmaster.com` and `www.amazon.com` under `en`, and `www.thefork.es`,
    `www.entradas.com` and `www.amazon.es` under `es`. A background detect fixes turn 2; the errand that goes
    out on turn 1 is already pointed at the wrong country.

    Returns the locked code, or None when nothing was done (already chosen, too short, classifier unsure).
    Never raises: a language guess must not be able to take down a turn.
    """
    try:
        if not should_detect():
            return None
        code = classify(text)
        if not code:
            return None
        import asyncio
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(lock(code))
            return code
        # Inside a running loop `lock()` cannot be awaited from here, and the part that matters for THIS turn
        # is the persist+env, which is synchronous anyway. The bundle prepare and the SSE switch are the UI's
        # half and can wait for the next start.
        from config import settings as _s
        _s.update({"stt_language": code})
        global _should_cache
        _should_cache = False
        logger.info(f"i18n.detect: text channel locked operator language -> '{code}'")
        return code
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: text-channel detection failed: {e}")
        return None


async def _priority_translate_loading(code: str) -> str | None:
    """Translate JUST `onboarding.loading` ahead of the full bundle, so a first-run onboarding modal can show
    already-translated loader text without waiting the ~10s-2min the full 562-key manifest can take. Persists
    the result into the generated store immediately so the full `ensure_language` diff (which runs right after)
    sees it as already-current and doesn't re-translate it a second time with possibly different phrasing."""
    from i18n import runtime as _rt
    if code in _rt.PRESET:
        return _rt.strings(code).get("onboarding.loading")
    man = _rt.manifest()
    key = "onboarding.loading"
    if key not in man:
        return None
    try:
        from i18n.init import generate as _generate
        from i18n import store as _store
        got = await _generate.translate(code, {key: man[key]})
        text = got.get(key)
        if text:
            gen = _store.read(code)
            strings = dict(gen.get("strings", {}))
            src = dict(gen.get("src", {}))
            strings[key] = text
            src[key] = man[key]
            _store.save(code, _rt.MANIFEST_VERSION, strings, src)
        return text
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: priority translate of '{key}' failed for '{code}': {e}")
        return None


async def lock(code: str, *, onboarding: bool = False) -> dict:
    """Commit the detected language: persist it, prepare its UI bundle (+ alias pack for non-preset languages,
    V2-101), and tell the frontend to switch. Idempotent enough — once persisted, should_detect() goes False so
    this won't fire again.

    `onboarding=True` (first-run language-choice flow) does two extra things: emits the SSE event EARLY, with an
    already-translated `loading` string, so a blocking modal can show real progress text instead of a bare
    spinner while the (possibly slow, for a non-preset language) full prepare runs in the background; and
    returns `confirm_text` (the bundle's `onboarding.confirmSpoken`, ready once prepare finishes) for the caller
    to speak out loud. Plain language switches (⚙, or repeat detection) skip the priority translate — the UI
    already has SOMETHING to show (the previous language) so there's no blocking modal waiting on it."""
    global _should_cache
    code = (code or "").strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}", code):
        return {"ok": False, "code": code}
    logger.info(f"i18n.detect: locking operator language → '{code}'" + (" (onboarding)" if onboarding else ""))
    try:
        from config import settings as _s
        _s.update({"stt_language": code})          # persist + env (voice realigns on next reconnect)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: settings.update failed: {e}")
    _should_cache = False                           # stop detecting
    # THE MEMORY'S CANONICAL LANGUAGE. Locking used to move the voice, the STT and the UI and leave the memory
    # behind: `state.language` is what `mem_processor._render` reads to decide the language every pill is written
    # in, and nothing here ever wrote it. So a French operator got French speech, French STT and a French UI —
    # while their memory was distilled, forever, into whatever the default happened to be. The memory is
    # deliberately MONOLINGUAL in the operator's language (2026-07-10); that only holds if detection moves it too.
    try:
        from memory import api as _memory
        _memory.set_state({"language": code})
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: could not set the memory's canonical language: {e}")

    loading_text = None
    if onboarding:
        loading_text = await _priority_translate_loading(code)
        try:
            from voice.observer import emit
            emit("language", "detected", role="system",
                 extra={"code": code, "phase": "detected", "loading": loading_text})
        except Exception:
            pass

    try:
        from i18n import init as _init
        await _init.prepare(code)                   # generate/upgrade the UI bundle (preset → instant)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"i18n.detect: prepare('{code}') failed: {e}")
    # Alias-pack generation (V2-101) is scoped to ONBOARDING only, not every lock() — a plain ⚙ switch or a
    # repeat background detection must stay exactly as cheap as it always was; this is deliberately not
    # "whenever the language changes" but "as part of the first-run setup ceremony".
    if onboarding:
        try:
            from i18n import runtime as _rt
            if code not in _rt.PRESET:
                from i18n.init import aliases as _aliases
                await _aliases.ensure_aliases(code)      # the widget-name voice-command pack
        except Exception as e:  # noqa: BLE001
            logger.warning(f"i18n.detect: alias pack for '{code}' failed: {e}")

    confirm_text = None
    try:
        from i18n import runtime as _rt
        confirm_text = _rt.strings(code).get("onboarding.confirmSpoken")
    except Exception:
        confirm_text = None

    try:
        from voice.observer import emit
        phase = "ready" if onboarding else "changed"
        emit("language", phase, role="system", extra={"code": code, "phase": phase})  # → frontend applyLang(code)
    except Exception:
        pass
    return {"ok": True, "code": code, "confirm_text": confirm_text}
