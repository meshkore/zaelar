"""V2-325 — asking a worker bridge for help is not making a mistake, but `widget_cli` treated it as an error.

MEASURED in the studio session logs (2026-08-25, full run):

    332 worker sessions · 81 use `nav_cli` · 5 reach `widget_cli` · of those 5, THREE die with Exit code 2

And the step that kills them is the FIRST ONE. From one of their logs, verbatim:

    [161] · paso ⚠️ error    Exit code 2 comando desconocido: --help
    [163] · paso ⚠️ error    Exit code 2 <manual de uso>

The worker types `widget_cli --help` —what anyone does with a new tool—, receives «unknown command» with code 2,
tries something else, fails again, and gives up. Its sibling `nav_cli` answers `--help` with exit 0 because it uses
argparse, and it is precisely the bridge that does get used (81 of 332).

WHY IT MATTERS MORE THAN IT SEEMS: `widget_cli` is the only way a worker can put into the sheet what it learns by
OPENING cards. Without it, the sheet is filled only with what the automatic extractor pulls from a listing. Measured
in the insurance round (20:22-20:32): the judge sees 8 options gathered, the sheet receives 2, and the brain prompt
carried the SAME two rows for nine turns in a row.

⚠️ WHAT THIS FIX DOES NOT PROVE: that workers will use the sheet now. It proves that a measured point of friction was
removed from their first action. The other thing is measured AFTERWARD, in the case — which is the rule that took
four fixes to learn today (see `CLAUDE.md`, V2-322).
"""
import subprocess
import sys

import pytest

_CLI = [sys.executable, "-m", "nucleo.widget_cli"]


def _correr(*args):
    p = subprocess.run(_CLI + list(args), capture_output=True, text=True, timeout=30)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


@pytest.mark.parametrize("verbo", ["--help", "-h", "help", "ayuda", "--ayuda", "-?", "/?"])
def test_pedir_ayuda_SALE_BIEN(verbo):
    """Zero, not two. The code is half the message: a model that sees `Exit code 2` concludes that it used the wrong
    tool, not that it has just been answered."""
    rc, out = _correr(verbo)
    assert rc == 0, f"`{verbo}` salió con {rc}"
    assert "widget_cli" in out and "read" in out


def test_y_TRAE_el_manual_no_solo_un_codigo():
    rc, out = _correr("--help")
    assert rc == 0
    for pista in ("read", "data", "show", "close", "@"):
        assert pista in out, f"el manual no menciona «{pista}»"


def test_un_verbo_QUE_NO_EXISTE_sigue_fallando():
    """The sensitivity check: if this changes to 0, the bridge stops reporting a real error and the worker thinks its
    call worked — which is worse than the defect V2-325 fixes."""
    rc, _ = _correr("inventado")
    assert rc == 2


def test_pero_el_error_DICE_qué_verbos_hay():
    """The same courtesy as `nav_cli._hint_for`: an error that does not show the way costs another full turn."""
    _, out = _correr("inventado")
    for verbo in ("read", "data", "show", "close"):
        assert verbo in out, f"el error no nombra «{verbo}»"
    assert "--help" in out


def test_sin_argumentos_sigue_siendo_un_error_de_uso():
    """Convention, and deliberate: invoking with nothing is NOT asking for help. `cmd` by itself → usage + 2, as in
    the entire ecosystem; `cmd --help` → help + 0. Changing the former would mean inventing a convention of its own."""
    rc, out = _correr()
    assert rc == 2
    assert "widget_cli" in out


def test_el_HERMANO_que_sí_se_usa_se_comporta_igual():
    """`nav_cli` is the reference, not my idea: 81 of 332 sessions use it and it answers `--help` with 0. This test
    ties the two bridges together so they do not diverge again at the entry point."""
    p = subprocess.run([sys.executable, "-m", "nucleo.nav_cli", "--help"],
                       capture_output=True, text=True, timeout=30)
    assert p.returncode == 0
