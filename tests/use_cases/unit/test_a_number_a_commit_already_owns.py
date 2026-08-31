"""V2-316 — a number already claimed by a COMMIT is not assigned again, even if its file does not exist.

`_next_initiative_number` read ONE record —the files— and there are two. The agent making the fix leaves its decision in
`engine/CLAUDE.md` and in the commit subject, and writes the initiative afterward (or, in a long batch, at
the end). Between those two moments the number appears free and this function assigns it.

Measured on 2026-08-25: here, `V2-312` was coined for `things-to-do-nearby-weekend__es` while V2-312 was already the
role-flip work, committed an hour earlier. Nothing failed, which is precisely the problem: two unrelated pieces of
history answer to the same name. It is the same failure that the note “archived items still own their number”
prevents through the other route.
"""
import re

from tests.use_cases.e2e.agent import initiative as I


def test_lee_los_numeros_del_LOG_no_solo_los_del_disco():
    n = I._numbers_claimed_by_commits()
    assert n, "sin números del log, la mitad del registro sigue invisible"
    assert all(isinstance(x, int) and 0 < x < 1000 for x in n)


def test_los_numeros_MEDIDOS_estan_reclamados():
    """314 and 315 were committed without an initiative file: they are exactly the case that creates this loophole."""
    n = I._numbers_claimed_by_commits()
    assert 314 in n and 315 in n


def test_el_siguiente_numero_los_RESPETA():
    """Half the wiring: the read can be correct and fail to reach the code that assigns numbers (V2-199)."""
    n = I._next_initiative_number()
    assert n not in I._numbers_claimed_by_commits()
    assert not list(I.INITIATIVES.rglob(f"V2-{n:03d}-*.md"))


def test_falla_ABIERTO_sin_git(monkeypatch):
    """Without git, archiving does not stop: losing a claim costs a collision that can be renumbered by hand;
    refusing to archive costs a measured defect that is not recorded anywhere."""
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
    """`V2-9` or `V2-1234` are not initiatives; counting them would pollute the assignment with numbers that do not exist."""
    class _R:
        returncode = 0
        stdout = "toca V2-042 y V2-9 y V2-12345 y v2-077"
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    assert I._numbers_claimed_by_commits() == {42}
