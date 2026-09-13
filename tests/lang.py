"""ONE way to make the suite speak a language — `speaking(code)` (V2-684, T-A).

The suite runs with `ZAELAR_LANGUAGE=en` forced (root `conftest.py`, and that decision stands: it comes
from a real 2026-08-10 failure where the operator's own `settings.json` decided what «green» meant). A
test that wants another language declares it — and until now five files each reinvented how, none of them
shared:

    tests/agent_headless/unit/test_confirm_gate_task.py::_es
    tests/agent_headless/unit/actionmap/test_a_known_phrase_skips_the_model.py::_lang
    tests/agent_headless/unit/flash/test_the_count_matches_the_names_it_gives.py::_es
    tests/infrastructure/unit/core/test_what_the_operator_hears_is_in_his_language.py::_in
    tests/infrastructure/unit/core/test_the_guardrails_speak_the_operators_language.py::_with_language

Between them they did the job THREE different ways, and only one called `actionmap.invalidate()` — so a
test that switched language while an action-map pack was cached measured the previous language's table and
could not tell. Changing the language is three things, not one, and this is the only place that knows it.

## The cache that cannot be reset, said out loud

`voice/engine/core/config.SETTINGS.language` freezes `ZAELAR_LANGUAGE` at the module's FIRST import and
has no reset function. Nothing here can undo that, and pretending otherwise is worse than saying it: a
test whose subject reads that object gets the language of whatever imported it first, and the only real
protection is import order (documented in `test_a_known_phrase_skips_the_model.py:21-28`).

## And a leak is a FAILURE, not the next test's problem

The root conftest installs a guard that asserts `ZAELAR_LANGUAGE` comes out of every test as it went in.
That closes the hole `test_first_run_language.py:99-101` has been documenting since 2026-08-20 instead of
merely recording it — `config/settings.update()` writes that variable unconditionally, so a test touching
settings could silently re-language every test after it. The test that dirties it fails, rather than
tinting its neighbour.
"""
from __future__ import annotations

import contextlib
import os

#: The two the repo SHIPS. A generated language is a different question (i18n/init/ensure.py).
LANGS = ("es", "en")


@contextlib.contextmanager
def speaking(code: str):
    """Make the engine speak `code` for the duration of the block, and put everything back.

    The three things, in one place:
      1. `ZAELAR_LANGUAGE` — what `langs.current_language()` reads live, per call, with no memoisation;
      2. `actionmap.invalidate()` — the pack is indexed BY LANGUAGE and cached, so without this a test
         measures the table of whichever language ran first;
      3. `detect._should_cache` — the first-run gate, whose `None` means «not decided yet».

    No `monkeypatch`: this is used from inside test bodies AND from a root-conftest fixture, and a
    root-conftest fixture's patches are undone AFTER any module fixture's teardown (the reason the two
    isolation fixtures beside it already save and restore by hand).
    """
    before = os.environ.get("ZAELAR_LANGUAGE")
    os.environ["ZAELAR_LANGUAGE"] = str(code)
    _invalidate()
    try:
        yield code
    finally:
        if before is None:
            os.environ.pop("ZAELAR_LANGUAGE", None)
        else:
            os.environ["ZAELAR_LANGUAGE"] = before
        _invalidate()


def _invalidate() -> None:
    """Drop every cache that is keyed on the language. Best-effort by design: a module that is not
    importable in this test's slice must not turn a language switch into an error."""
    try:
        from nucleo import actionmap
        actionmap.invalidate()
    except Exception:
        pass
    try:
        from i18n.init import detect
        detect._should_cache = None
    except Exception:
        pass
