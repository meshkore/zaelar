"""A traceback truncated from the front preserves the scaffolding and throws away the exception.

Measured on 2026-08-28 on the board: the three tracebacks recorded as «done» certainty anomalies
ended up like this —

    Traceback (most recent call last): File "<frozen runpy>", line 198, in _run_module_as_main
    File "<frozen runpy>", line 88, in _run_code File "/Users…

— one hundred characters of scaffolding **identical in any Python failure**, and the exception line, which is
the only part that says anything, cut off. Three recorded facts and none diagnosable: the report stated
that there was an internal error and did not allow anyone to know which one, which is the most expensive way to be right.

In a traceback, the useful part is at the END. In any other text it is at the beginning, and there the usual truncation
is correct — which is why this is not «truncating from the back», but «truncating from whichever end is appropriate».
"""
from __future__ import annotations

from tests.use_cases.e2e.agent.verify import _error_gist

_TB = ("Traceback (most recent call last): "
       'File "<frozen runpy>", line 198, in _run_module_as_main '
       'File "<frozen runpy>", line 88, in _run_code '
       'File "/Users/x/engine/nucleo/nav_cli.py", line 412, in <module> ' + "relleno " * 30 +
       "TypeError: Page.goto() expected str, got NoneType")


def test_de_un_traceback_se_queda_la_EXCEPCION():
    got = _error_gist(_TB)
    assert "TypeError: Page.goto() expected str, got NoneType" in got
    assert "_run_module_as_main" not in got, "el andamiaje se comía el presupuesto entero"


def test_y_se_MARCA_que_venía_recortado():
    """An error that begins halfway through a sentence without warning reads as a different error from the original."""
    assert _error_gist(_TB).startswith("…")


def test_un_error_normal_se_recorta_por_DELANTE():
    """The sensitivity trade-off: in an ordinary message the important part comes first, and reversing everything
    would break the other nine errors on the board to fix three."""
    largo = "ERROR: ref 30 no está en la mirada actual, que tiene 1..8. " + "detalle " * 60
    got = _error_gist(largo)
    assert got.startswith("ERROR: ref 30") and not got.startswith("…")


def test_lo_que_CABE_se_deja_entero():
    corto = "Exit code 2 no puedo leer el payload de progreso.json"
    assert _error_gist(corto) == corto


def test_el_auditor_lo_USA():
    """The plumbing: if the auditor keeps cutting blindly, the function exists and fixes nothing."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text(encoding="utf-8")
    assert "_error_gist(e['text'])" in src
    assert "e['text'][:160]" not in src, "el recorte viejo sigue vivo en el auditor"
