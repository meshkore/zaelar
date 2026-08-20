"""Un número ARCHIVADO sigue siendo suyo para siempre.

Escrito el 2026-08-20, al archivar el tablero: 87 iniciativas terminales y 210 tareas se movieron a
`archive/`, y los dos asignadores de números buscaban con `glob` NO recursivo. Sin recursión, archivar la
iniciativa más alta hace que su número vuelva a estar libre.

Y el daño de reutilizar un número aquí es del tipo caro: nada falla, nada sale en rojo. Simplemente dos
trozos de historia sin relación responden al mismo nombre, y cada referencia cruzada escrita ANTES de la
reutilización —en una tarea, en un commit, en `CLAUDE.md`— pasa a apuntar silenciosamente a la otra.

⚠️ Estos tests montan el tablero en un directorio TEMPORAL a propósito. La primera versión afirmaba lo
mismo contra el disco real y pasaba con el `glob` roto: hoy los números archivados están todos por DEBAJO
del máximo vivo, así que `max+1` los esquiva por accidente y el test no medía nada. La situación peligrosa
—el número más alto viviendo SOLO en `archive/`— es justo la que llega cuando se cierre V2-201, y hay que
construirla, no esperarla.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import initiative as I


@pytest.fixture
def board(tmp_path, monkeypatch):
    """Un tablero donde lo más alto que se ha usado nunca está ARCHIVADO, no vivo."""
    inis = tmp_path / "initiatives"
    (inis / "archive").mkdir(parents=True)
    (inis / "V2-150-algo-vivo.md").write_text("---\nstatus: open\n---\n")
    (inis / "archive" / "V2-201-lo-ultimo-que-se-cerro.md").write_text("---\nstatus: closed\n---\n")

    mods = tmp_path / "modules"
    (mods / "nucleo" / "tasks" / "archive").mkdir(parents=True)
    (mods / "nucleo" / "tasks" / "T300-viva.md").write_text("---\nstatus: next\n---\n")
    (mods / "nucleo" / "tasks" / "archive" / "T441-la-ultima-cerrada.md").write_text("---\nstatus: done\n---\n")

    monkeypatch.setattr(I, "INITIATIVES", inis)
    monkeypatch.setattr(I, "MODULES", mods)
    return tmp_path


def test_the_number_of_an_archived_initiative_is_never_reissued(board):
    assert I._next_initiative_number() == 202, (
        "V2-201 está archivada, no borrada: su número sigue ocupado. Reemitirlo deja dos iniciativas "
        "distintas respondiendo al mismo nombre")


def test_the_number_of_an_archived_task_is_never_reissued(board):
    assert I._next_task_number() == 442, "T441 está archivada; su número sigue ocupado"


def test_and_the_live_board_still_moves_the_counter(board):
    """La mitad de sensibilidad: mirar dentro del archivo no puede hacer que se IGNORE el tablero vivo."""
    (board / "initiatives" / "V2-300-mas-alta-y-viva.md").write_text("---\nstatus: open\n---\n")
    assert I._next_initiative_number() == 301
