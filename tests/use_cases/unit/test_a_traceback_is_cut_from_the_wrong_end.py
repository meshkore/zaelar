"""Un traceback recortado por delante conserva el andamiaje y tira la excepción.

Medido el 2026-08-28 sobre el tablero: los tres tracebacks guardados como anomalías de certeza «hecho»
quedaron así —

    Traceback (most recent call last): File "<frozen runpy>", line 198, in _run_module_as_main
    File "<frozen runpy>", line 88, in _run_code File "/Users…

— cien caracteres de andamiaje **idéntico en cualquier fallo de Python**, y la línea de la excepción, que es
la única que dice algo, cortada fuera. Tres hechos registrados y ninguno diagnosticable: el informe afirmaba
que había un error interno y no permitía saber cuál, que es la forma más cara de tener razón.

En un traceback lo que sirve está al FINAL. En cualquier otro texto está al principio, y ahí el recorte de
siempre es el correcto — por eso esto no es «recortar por detrás», es «recortar por donde toque».
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
    """Un error que empieza a media frase sin avisar se lee como un error distinto del que fue."""
    assert _error_gist(_TB).startswith("…")


def test_un_error_normal_se_recorta_por_DELANTE():
    """La mitad de sensibilidad: en un mensaje corriente lo importante va primero, y darle la vuelta a todo
    rompería los otros nueve errores del tablero para arreglar tres."""
    largo = "ERROR: ref 30 no está en la mirada actual, que tiene 1..8. " + "detalle " * 60
    got = _error_gist(largo)
    assert got.startswith("ERROR: ref 30") and not got.startswith("…")


def test_lo_que_CABE_se_deja_entero():
    corto = "Exit code 2 no puedo leer el payload de progreso.json"
    assert _error_gist(corto) == corto


def test_el_auditor_lo_USA():
    """La fontanería: si el auditor sigue cortando a pelo, la función existe y no arregla nada."""
    from pathlib import Path
    src = Path("tests/use_cases/e2e/agent/verify.py").read_text(encoding="utf-8")
    assert "_error_gist(e['text'])" in src
    assert "e['text'][:160]" not in src, "el recorte viejo sigue vivo en el auditor"
