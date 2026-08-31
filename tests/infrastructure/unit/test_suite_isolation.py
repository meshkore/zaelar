"""
THE SUITE DOES NOT DEPEND ON THE MACHINE IT RUNS ON — a guard over the guards.

This originated with a green test that LIED (2026-08-10). Two cases (`test_music_flow`, `test_prompt`) checked phrases
spoken to the operator without fixing the language: they passed on a machine configured for Spanish and would have
failed anywhere else and in CI. Fixing it revealed that the cause was broader than the language —
`config/settings.load_into_env()` copies `config/settings.json` ON TOP OF the environment unconditionally, because in
production the store OVERRIDES the env (the correct rule there). In a test, that means the operator's personal
configuration —language, STT/TTS provider, attention mode, engine profile— determines the suite's result as soon as
something in the import graph calls that function.

It was not that it failed: it was that **the green result could not be trusted**, which is worse. The same family as an
unisolated fixture that deleted the widgets' real data, or two nodes in the test map with the same number.

This file establishes the test-session isolation invariants. If any of them breaks, the suite can lie again — and no one
would find out until a test passed here and failed somewhere else.
"""
from __future__ import annotations

import os
from pathlib import Path


def test_the_language_is_the_products_own_default_not_the_operators():
    """It runs in the language with which the product STARTS, which is the state of any new installation. A test that
    wants another language declares it itself — and then what it tests is explicit."""
    from voice.engine.core import langs

    assert langs.current_code() == langs.DEFAULT_LANG == "en"


def test_the_operators_settings_file_is_not_the_one_the_suite_reads():
    from config import settings

    p = str(settings.SETTINGS_FILE)
    assert "zaelar-test-settings-" in p, (
        "la suite está leyendo el `settings.json` REAL: la configuración del operador puede cambiar el resultado "
        f"de los tests (y en producción el store pisa el entorno a propósito). Apunta a: {p}")
    assert not Path(settings.SETTINGS_FILE).exists(), "y el fichero de la suite arranca VACÍO, no copiado"


def test_loading_the_settings_cannot_flip_the_suite():
    """The acid test: calling what the real startup does cannot change the language out from under the suite."""
    from config import settings
    from voice.engine.core import langs

    settings.load_into_env()
    assert langs.current_code() == "en"


def test_the_logs_of_a_test_never_land_in_the_operators_timeline():
    """It already existed (2026-07-25: a test's «kind:error boom» was read as a real incident) and is checked here
    so that the isolation invariants live together and can be read in one place."""
    d = os.getenv("ZAELAR_LOG_DIR") or ""
    assert "zaelar-test-logs-" in d, f"los eventos de la suite irían al timeline real: {d!r}"


def test_the_operators_widget_data_is_not_the_one_the_suite_writes():
    """The widgets' DATA was the last place where this file's invariant —«a test never reads or writes the operator's
    real state»— was not enforced at the SESSION level. `conftest.py` itself already cited `store.DATA_DIR` as the same
    lesson, but only within the widget tests: any other test that dispatched a data-op wrote to the REAL agenda.

    Measured on 2026-08-20: **328 appointments** «renovar el seguro del coche» accumulated in the operator's agenda, and
    **2 more for each full run**. None of them broke anything — the junk stays there and is noticed only when
    someone looks at their agenda, or when a new fix starts to READ IT and suddenly nine tests depend on the
    order in which the previous ones ran. Which is exactly what happened.
    """
    from widgets import store

    # Check what MATTERS —that it is not the operator's— rather than a specific prefix: the widget tests
    # point `DATA_DIR` at THEIR own temporary directory and do not restore it, so requiring the `conftest`
    # prefix made execution order the source of the failure. Any temporary directory is fine; the real one is not.
    real = Path(__file__).resolve().parents[3] / "widgets" / "_data"
    assert Path(store.DATA_DIR).resolve() != real.resolve(), (
        "la suite está escribiendo en los datos de widgets REALES del operador: una data-op de cualquier test "
        f"le deja basura en su agenda. Apunta a: {store.DATA_DIR}")
