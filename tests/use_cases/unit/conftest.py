"""Ningún test unitario puede escribir en los artefactos VIVOS de la campaña.

Escrito el 2026-08-20 tras encontrar el porqué de una anomalía que llevaba un día sin explicación: el log
del bucle mostraba «ticks» a las 02:46, 10:19, 10:24 y 10:25 que clasificaban un caso como BLOQUEADO con
sellos de tiempo del pasado (`'01:00'→'02:20'`), y no había ningún proceso de tick corriendo. No eran ticks:
era `test_blocked_filing.py` llamando a `_retest_pending()` sin interceptar `_log`, así que **cada corrida de
la suite unitaria escribía en el log que el operador lee** — con las horas de su ledger simulado.

El daño es del tipo que cuesta encontrar: el log del bucle es la única prueba de qué se midió y cuándo, y
unas líneas falsas ahí no rompen nada, solo hacen que la evidencia mienta. Se arregla en el CONFTEST y no
test a test, porque el siguiente test que llame a una función del tick volvería a hacerlo sin enterarse.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import status as statusmod, tick as T


_LIVE_LEDGER = statusmod.LEDGER_PATH
_LIVE_BOARD = statusmod.BOARD_PATH


@pytest.fixture(autouse=True)
def _never_touch_live_artifacts(tmp_path, monkeypatch):
    """Por defecto, TODO apunta a un directorio temporal. El log del tick no tiene excepción posible."""
    monkeypatch.setattr(T, "LOG_PATH", tmp_path / "tick.log")
    monkeypatch.setattr(statusmod, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(statusmod, "BOARD_PATH", tmp_path / "STATUS.md")
    yield


@pytest.fixture
def live_board(monkeypatch):
    """Opt-in EXPLÍCITO para los pocos tests que afirman un invariante del tablero REAL (p. ej. «ningún caso
    ya juzgado sigue en la cola»). Devuelve las rutas de verdad, y solo para LEER.

    Es opt-in y no lo contrario a propósito: un test que se olvide de aislarse no puede volver a escribir en
    los artefactos vivos, y un test que necesite el tablero real tiene que decirlo en su firma, donde se ve.
    """
    monkeypatch.setattr(statusmod, "LEDGER_PATH", _LIVE_LEDGER)
    monkeypatch.setattr(statusmod, "BOARD_PATH", _LIVE_BOARD)
    return _LIVE_LEDGER
