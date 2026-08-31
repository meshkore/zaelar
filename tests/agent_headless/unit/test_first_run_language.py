"""A text-only channel has no way to ASK what language to speak (V2-170).

The voice pipeline opens a brand-new install with a blocking question — «what language should I use?» — and
locks the answer. A text channel gets no such turn, so before this it simply stayed on the product default
(English) for as long as it lived. Two things live there that are NOT cosmetic:

  · the Brain Worker's closing instruction is literally «ESCRIBE tu conclusión final en <native>», so a
    Spanish errand came back in English;
  · `nucleo/flash/site_catalog.py` resolves its LOCALE from the same code, so the genetic catalogue handed a
    Spanish errand `www.opentable.com`, `www.ticketmaster.com` and `www.amazon.com` where `es` would have
    handed it `www.thefork.es`, `www.entradas.com` and `www.amazon.es`.

That second one is the expensive half, and it is measured, not argued: the live theatre run of 2026-08-19
opened Ticketmaster and reported back «it barely lists any Spanish theatre right now» — which is true, and is
what being sent to the wrong country's site looks like from the inside.

Verified in a live sandbox on 2026-08-20: `active: en, chosen: false` → one Spanish message → `active: es`,
reply in Spanish, 5.4 s. And an English first message keeps `en`, which is the half that would otherwise pass
by accident.
"""
from __future__ import annotations

import pytest

from i18n.init import detect


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(detect, "_should_cache", None, raising=False)
    yield


def _no_lock(monkeypatch, seen: dict):
    monkeypatch.setattr("config.settings.update", lambda payload: seen.update(payload) or payload)


def test_a_first_run_text_channel_locks_what_it_reads(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(detect, "should_detect", lambda: True)
    monkeypatch.setattr(detect, "classify", lambda t: "es")
    _no_lock(monkeypatch, seen)
    assert detect.ensure_for_text("Búscame un hotel en Madrid") == "es"
    assert seen == {"stt_language": "es"}


def test_and_stops_detecting_afterwards(monkeypatch):
    """The gate is the whole safety of this: it must fire once on a fresh install and never again, or every
    turn would pay a classify and a stray English sentence could flip a Spanish operator's engine."""
    monkeypatch.setattr(detect, "should_detect", lambda: True)
    monkeypatch.setattr(detect, "classify", lambda t: "es")
    _no_lock(monkeypatch, {})
    detect.ensure_for_text("Búscame un hotel en Madrid")
    assert detect._should_cache is False
    assert detect.should_detect.__name__  # sanity: we replaced it, the real gate reads _should_cache


def test_an_already_chosen_language_is_never_touched(monkeypatch):
    """The deliberate-choice invariant of `detect`: auto-detection NEVER overrides a language the operator
    picked in ⚙."""
    called = []
    monkeypatch.setattr(detect, "should_detect", lambda: False)
    monkeypatch.setattr(detect, "classify", lambda t: called.append(t) or "es")
    assert detect.ensure_for_text("Búscame un hotel en Madrid") is None
    assert called == []


def test_an_unsure_classifier_changes_nothing(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(detect, "should_detect", lambda: True)
    monkeypatch.setattr(detect, "classify", lambda t: None)
    _no_lock(monkeypatch, seen)
    assert detect.ensure_for_text("...") is None
    assert seen == {}


def test_and_a_classifier_that_explodes_does_not_take_the_turn_with_it(monkeypatch):
    """Fail-open by construction: this runs at the very top of a turn, so anything it raises would kill a turn
    that had nothing to do with language."""
    def _boom(_t):
        raise RuntimeError("el clasificador se cayó")
    monkeypatch.setattr(detect, "should_detect", lambda: True)
    monkeypatch.setattr(detect, "classify", _boom)
    assert detect.ensure_for_text("Búscame un hotel en Madrid") is None


# ── and that the text channel actually CALLS it ────────────────────────────────────────────────────────────
def test_the_text_channel_actually_calls_it():
    """The other half, and the one that would have kept this dead: a detector nobody invokes is exactly the
    state the engine was already in — `i18n.init.detect` existed and worked, and only the voice pipeline ever
    reached it."""
    import inspect

    from nucleo.flash import probe_api
    assert "ensure_for_text" in inspect.getsource(probe_api.say)


def test_but_NOT_from_run_turn_itself(monkeypatch):
    """Where it hangs is load-bearing, and this is the test that pins it. `run_turn` is also how the suite
    drives a turn in-process, so a language lock fired from there persists `stt_language` into the session's
    settings file and flips `ZAELAR_LANGUAGE` for every test that runs afterwards — measured on 2026-08-20:
    three assertions of `test_suite_isolation.py` went red and a Spanish-sensitive backstop test with them.
    The HTTP edge is where a real operator is on the other side; `run_turn` is a library function."""
    import inspect

    from nucleo.flash import probe
    assert "ensure_for_text" not in inspect.getsource(probe.run_turn)


def test_but_the_voice_provider_does_NOT(monkeypatch):
    """Deliberate asymmetry, and it is a REGRESSION GUARD, not an oversight: the voice pipeline asks the
    operator behind a blocking modal (V2-101). A silent lock on that side would race the question and could
    commit the wrong language before it has been answered."""
    import inspect

    from voice.engine.llm.providers import nucleo as _provider
    assert "ensure_for_text" not in inspect.getsource(_provider)


def test_the_locale_of_the_site_catalog_follows_the_language():
    """Why any of this matters, asserted rather than asserted-about: the two catalogues are genuinely
    different countries, so getting the language wrong sends a real errand to the wrong site."""
    from nucleo.flash import site_catalog as sc

    assert sc.resolve_locale("es") == "es"
    assert sc.resolve_locale("en") == "us"
    es, us = sc.directive_block("es"), sc.directive_block("us")
    assert "thefork.es" in es and "thefork.es" not in us
    assert "opentable.com" in us and "opentable.com" not in es


# ── The classifier's REPLY is parsed, and that parse was the bug (2026-08-21) ─────────────────────────────
# `_by_llm` used to take the first two lowercase letters found ANYWHERE in the reply, so a preamble became the
# answer — and every wrong answer it produced is a valid ISO code, which is why nothing downstream ever caught
# it. Seen live once in 66 saved rounds, on the run whose providers were down: the classifier only replies with
# a sentence when the model is degraded or relaying. `es` -> `it` locks the operator into Italian, silently and
# for good (`should_detect()` goes False), and points `site_catalog` at the wrong country.

@pytest.mark.parametrize("reply, expected", [
    # The healthy path — 65 of those 66 rounds. Must keep working: a parse too strict trades one bug for another.
    ("es", "es"), ("ES", "es"), ("'es'", "es"), ("es.", "es"), ("  es  ", "es"), ("es (Spanish)", "es"),
    # Recoverable: exactly ONE two-letter word, so there is nothing to be wrong about.
    ("Language: es", "es"), ("Sure, es", "es"),
    # The six measured failures. Each USED to yield a real ISO code for a language nobody speaks here.
    ("It is Spanish (es)", None),      # was 'it'  — Italian, the one seen live
    ("It's 'es'", None),               # was 'it'
    ("The language is es.", None),     # was 'th'  — Thai
    ("Spanish", None),                 # was 'sp'  — not even a code
    ("It is", None),                   # was 'it'  — the degraded reply truncated by max_tokens=4
    # Nothing to read.
    ("", None), (None, None), ("   ", None),
])
def test_a_reply_yields_a_code_only_when_it_is_unambiguous(reply, expected):
    assert detect.extract_code(reply) == expected


def test_the_token_ceiling_is_high_enough_that_a_sentence_stays_a_sentence():
    """The hole left open by the first fix (2026-08-21, seen LIVE at 10:12 with `extract_code`
    already in the tree: the sandbox persisted `stt_language: "it"` in a Spanish run).

    `extract_code` rejects a SENTENCE («It is Spanish (es)» has three two-letter words → ambiguous). But with
    `max_tokens=4` that sentence does not arrive in full: **«It»** arrives, a single word the anchor accepts because `it`
    IS the Italian code. In other words, truncation turned a rejectable answer into an accepted and
    wrong one. The ceiling is part of the fix, not a cost parameter — which is why it is monitored here.
    """
    import inspect

    fuente = inspect.getsource(detect._by_llm)
    assert "max_tokens=4," not in fuente, "un techo de 4 trunca la frase a «It» y eso se bloquea como italiano"
    assert detect.extract_code("It") == "it"          # the anchor CANNOT distinguish it: `it` is a real language
    assert detect.extract_code("It is Spanish (es)") is None   # in full, it is rejected — hence the ceiling matters


def test_a_refusal_is_not_a_dead_end():
    """Refusing costs a retry; a wrong lock is silent and permanent. Nothing is persisted when we refuse, so
    `should_detect()` stays True and the next utterance tries again."""
    assert detect.extract_code("It is Spanish (es)") is None
    assert detect.should_detect() is True


def test_validating_against_a_list_of_iso_codes_would_not_have_caught_it():
    """Guards the REASONING, so nobody 'improves' this later by adding an ISO whitelist and calls it fixed:
    every wrong answer the old parse produced is a real, spoken language."""
    for code in ("it", "th", "la", "su"):
        assert len(code) == 2 and code.isalpha()     # all four are valid ISO-639-1 — the whitelist lets them in
    assert detect.extract_code("The language is es.") is None   # only the ANCHOR rejects them
