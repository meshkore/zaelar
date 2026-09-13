"""V2-684 T-A — ONE way to change the suite's language, and a leak is a failure.

Two properties, and the second is the one with teeth:

  · `tests.lang.speaking(code)` does the THREE things a language change actually is — the environment
    variable, the action-map pack (indexed BY language and cached), and the first-run gate — and puts all
    three back. Five files each did some subset of this by hand, and only one of them invalidated the pack.
  · a test that leaves `ZAELAR_LANGUAGE` changed FAILS, by name, instead of quietly re-languaging every
    test that runs after it. That hole has been documented in prose since 2026-08-20
    (`test_first_run_language.py:99-101`) and nothing turned it red. Installing the guard found two real
    leaks the same afternoon: one file popped the variable entirely in its teardown, and two cases called
    `settings.update({"stt_language": "de"})`, which writes the process env on purpose.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.lang import LANGS, speaking

ROOT = Path(__file__).resolve().parents[4]


def test_speaking_sets_the_language_and_puts_it_back():
    before = os.environ.get("ZAELAR_LANGUAGE")
    with speaking("es"):
        assert os.environ["ZAELAR_LANGUAGE"] == "es"
        from i18n import langs
        assert langs.current_language().code == "es", "and the product reads it live, per call"
    assert os.environ.get("ZAELAR_LANGUAGE") == before


def test_speaking_NESTS_without_losing_the_outer_one():
    with speaking("es"):
        with speaking("en"):
            assert os.environ["ZAELAR_LANGUAGE"] == "en"
        assert os.environ["ZAELAR_LANGUAGE"] == "es", "the inner block restores ITS caller, not the suite"


def test_speaking_DROPS_the_action_map_pack_which_is_cached_per_language():
    """The half four of the five hand-rolled helpers forgot. Without it a test that switches language reads
    the table of whichever language was loaded first — and passes, describing the wrong language."""
    from nucleo import actionmap
    calls = []
    real = actionmap.invalidate
    actionmap.invalidate = lambda: calls.append(1)
    try:
        with speaking("es"):
            pass
    finally:
        actionmap.invalidate = real
    assert len(calls) == 2, "invalidated on the way in AND on the way out — both sides are a language change"


def test_both_shipped_languages_answer_the_same_question():
    """A minimal parity smoke: whatever else differs, the language the engine reports is the one asked for."""
    from i18n import langs
    for code in LANGS:
        with speaking(code):
            assert langs.current_language().code == code


def test_a_test_that_leaks_the_language_FAILS_instead_of_tinting_the_next_one(tmp_path):
    """Measured by running pytest, because a fixture cannot be believed from inside the run it governs.

    The leaking case PASSES its own assertion and still ends in an error — which is the whole design: the
    file that dirties the environment is the one that gets named, rather than whichever neighbour happens
    to run next and measure a language nobody chose.
    """
    case = tmp_path / "test_leaky.py"
    case.write_text(
        "import os\n"
        "def test_it_leaks():\n"
        "    os.environ['ZAELAR_LANGUAGE'] = 'de'\n"
        "    assert True\n", encoding="utf-8")
    # `-p conftest` loads the REAL root conftest as a plugin: a file outside the repo tree would not pick
    # it up by directory ancestry, and copying the guard into the fixture would prove the copy works.
    r = subprocess.run([sys.executable, "-m", "pytest", str(case), "-q", "--no-header", "-p", "conftest"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode != 0, "a language leak has to be a red run"
    assert "ZAELAR_LANGUAGE" in (r.stdout + r.stderr), "and it has to say which variable and what it became"


def test_the_root_conftest_really_installs_the_guard():
    """Read comment-stripped: explaining this rule in prose must not be what satisfies it (V2-615's trap)."""
    import re
    src = (ROOT / "conftest.py").read_text(encoding="utf-8")
    code = re.sub(r"#[^\n]*", "", re.sub(r'"""(?:.|\n)*?"""', "", src))
    assert "_a_language_leak_is_a_failure" in code and "autouse=True" in code
