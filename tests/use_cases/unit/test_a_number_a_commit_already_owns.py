"""V2-316 — un número que ya reclamó un COMMIT no se reparte otra vez, aunque no exista su fichero.

`_next_initiative_number` leía UN registro —los ficheros— y hay dos. El agente que arregla deja su decisión en
`engine/CLAUDE.md` y en el asunto del commit, y escribe la iniciativa después (o, en una tanda larga, en el
cierre). Entre esos dos momentos el número parece libre y esta función lo entrega.

Medido el 2026-08-25: aquí se acuñó `V2-312` para `things-to-do-nearby-weekend__es` mientras V2-312 era ya el
trabajo de role-flip, commiteado una hora antes. No falló nada, que es justo el problema: dos trozos de historia
sin relación responden al mismo nombre. Es la misma avería que la nota de «archivado sigue siendo dueño de su
número» previene por la otra puerta.
"""
import re

from tests.use_cases.e2e.agent import initiative as I


def test_lee_los_numeros_del_LOG_no_solo_los_del_disco():
    n = I._numbers_claimed_by_commits()
    assert n, "sin números del log, la mitad del registro sigue invisible"
    assert all(isinstance(x, int) and 0 < x < 1000 for x in n)


def test_los_numeros_MEDIDOS_estan_reclamados():
    """314 y 315 se commitearon sin fichero de iniciativa: son exactamente el caso que abre este agujero."""
    n = I._numbers_claimed_by_commits()
    assert 314 in n and 315 in n


def test_el_siguiente_numero_los_RESPETA():
    """La mitad de cableado: la lectura puede acertar y no llegar a quien reparte (V2-199)."""
    n = I._next_initiative_number()
    assert n not in I._numbers_claimed_by_commits()
    assert not list(I.INITIATIVES.rglob(f"V2-{n:03d}-*.md"))


def test_falla_ABIERTO_sin_git(monkeypatch):
    """Sin git no se deja de archivar: perder una reclamación cuesta una colisión que se renumera a mano;
    negarse a archivar cuesta un defecto medido que no queda registrado en ninguna parte."""
    def _boom(*a, **k):
        raise OSError("no git here")
    import subprocess
    monkeypatch.setattr(subprocess, "run", _boom)
    assert I._numbers_claimed_by_commits() == set()
    assert isinstance(I._next_initiative_number(), int)


def test_un_log_sin_numeros_no_inventa_ninguno(monkeypatch):
    class _R:
        returncode = 0
        stdout = "fix(web): arregla el botón\n\nnada que ver con iniciativas"
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert I._numbers_claimed_by_commits() == set()


def test_solo_casa_el_formato_de_TRES_digitos(monkeypatch):
    """`V2-9` o `V2-1234` no son iniciativas; contarlas envenenaría el reparto con números que no existen."""
    class _R:
        returncode = 0
        stdout = "toca V2-042 y V2-9 y V2-12345 y v2-077"
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert I._numbers_claimed_by_commits() == {42}
