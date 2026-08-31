"""A verb that targets a URL, without the URL, only gave the SYNTAX — and the worker repeated the mistake (V2-369).

Measured on `rental-car-automatic-airport__es` (2026-08-27, supervisor round, 2/5). Seven contract errors
with our own bridges in the first three minutes, including the measurement that determines this fix:

    t=32,4 s   nav_cli navigate: error: the following arguments are required: url
    t=74,3 s   nav_cli navigate: error: the following arguments are required: url     ← el MISMO, 42 s después
    t=90,0 s   nav_cli visit:    error: the following arguments are required: url

In the SAME session, bare `worker_bridge act` —which DOES include a guided hint—failed once and **was not repeated**.
Those that receive a hint correct themselves; those that only receive the `usage:` repeat the mistake. `_hint_for`
covered `type_at`, `scroll`, and `click_at` (the three arity confusions measured by V2-341), but covered none of the
verbs that target an address.

The cost: the task did not reach a single rental site. What ended up in the sheet were the eight titles
from the search-results page, and the judge counted them as candidates and accused the turn of not
delivering them — the instrument accusing the product of not offering “Rental requirements and qualifications”
as though it were a car.

It is node 4.20’s contract once again: whatever the bridge KNOWS, it says, and a failure also says how to recover.
"""
import subprocess
import sys

import pytest

from nucleo.nav_cli import _hint_for


def _pista(verbo: str) -> str:
    return _hint_for(f"nav_cli {verbo}")


@pytest.mark.parametrize("verbo", ["navigate", "open", "goto", "visit"])
def test_todo_verbo_de_direccion_dice_como_salir(verbo):
    """`open` and `goto` are ALIASES for `navigate` — covering only the canonical name leaves two doors open."""
    p = _pista(verbo)
    assert p, f"«{verbo}» va a una dirección y no dice nada"
    assert "https://" in p, "sin un ejemplo con esquema, «entera» es una palabra"
    assert "MISMO comando" in p


@pytest.mark.parametrize("verbo", ["navigate", "visit"])
def test_la_pista_NOMBRA_al_verbo_que_falló(verbo):
    """A hint that talks about another command tells the worker to type the wrong one."""
    assert f"`{verbo} https://" in _pista(verbo)


def test_la_pista_PROHIBE_repetirlo_igual():
    """The 42 seconds between the two bare `navigate` commands are exactly this: the natural reaction to a failure is
    to repeat it, and here repeating it can NEVER work."""
    assert "NO lo repitas igual" in _pista("navigate")


def test_no_se_le_invita_a_inventarse_una_direccion():
    """The symmetric failure, and it would be worse: a worker that makes up a URL navigates to a page that
    does not exist and counts it as a completed step (V2-253: acting with an invented argument)."""
    assert "no adivines" in _pista("navigate")


@pytest.mark.parametrize("verbo", ["click", "type", "extract", "snapshot", "look"])
def test_un_verbo_que_NO_va_a_una_direccion_no_recibe_esta_pista(verbo):
    """Sensitivity on the other side: a hint about addresses attached to `click` is noise, and a worker
    learns to skip hints that are irrelevant."""
    assert "LA DIRECCIÓN" not in _pista(verbo)


def test_las_pistas_de_V2_341_siguen_donde_estaban():
    """This change ADDS a branch; if it takes out the ones that were already there, it turns one defect into three."""
    assert "COORDENADAS" in _pista("type_at")
    assert "PÍXELES" in _pista("scroll")
    assert "COORDENADAS" in _pista("click_at")


def test_el_CLI_REAL_la_imprime_y_ANTES_del_usage():
    """The real path, not the predicate: `_hint_for` can be perfect and not be wired in. And order matters —
    a worker reads from top to bottom, so the output has to arrive before the syntax wall it is already looking at
    (this is the contract of `bridge_usage.guided`)."""
    r = subprocess.run([sys.executable, "-m", "nucleo.nav_cli", "navigate"],
                       capture_output=True, text=True)
    assert r.returncode == 2
    err = r.stderr
    assert "LA DIRECCIÓN" in err, "la pista no llega al worker"
    assert err.index("LA DIRECCIÓN") < err.index("usage:"), "la salida llega después del muro"
