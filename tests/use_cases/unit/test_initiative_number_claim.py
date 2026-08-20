"""Reading the highest number closes the read side of the race; the WRITE side is the one that bites.

Three collisions on 2026-08-20 — V2-170, then V2-216 and V2-217 against the fixing agent's work — each
renumbered by hand afterwards. The window is not theoretical: between picking the number and writing the file
there are a dozen lines and another piece of disk I/O (`claim_task`), and the other agent files initiatives of
its own the whole time.

A duplicated number is the worst kind of collision here. Nothing errors, two unrelated pieces of history answer
to the same name, and every cross-reference written before the reuse silently points at the wrong one.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import initiative as I


def test_two_claims_in_a_row_never_share_a_number(tmp_path, monkeypatch):
    monkeypatch.setattr(I, "INITIATIVES", tmp_path / "initiatives")
    n1, p1 = I.claim_initiative("caso-a")
    n2, p2 = I.claim_initiative("caso-b")
    assert n1 != n2, "dos reservas seguidas se llevaron el mismo número"
    assert p1.exists() and p2.exists()


def test_the_file_exists_the_INSTANT_the_number_is_handed_out(tmp_path, monkeypatch):
    """The whole point: if only the number came back, the window would stay open until somebody wrote."""
    monkeypatch.setattr(I, "INITIATIVES", tmp_path / "initiatives")
    n, p = I.claim_initiative("caso")
    assert p.exists(), "el número se entregó sin reservar el fichero: la carrera sigue abierta"
    assert p.name == f"V2-{n:03d}-uc-caso.md"


def test_a_number_taken_under_ANOTHER_slug_is_skipped(tmp_path, monkeypatch):
    """This is the collision that actually happened: same number, different subject, no error anywhere."""
    inits = tmp_path / "initiatives"
    inits.mkdir()
    monkeypatch.setattr(I, "INITIATIVES", inits)
    n = I._next_initiative_number()
    (inits / f"V2-{n:03d}-otro-asunto-del-otro-agente.md").write_text("del otro agente")
    got, path = I.claim_initiative("mi-caso")
    assert got > n
    assert (inits / f"V2-{n:03d}-otro-asunto-del-otro-agente.md").read_text() == "del otro agente"


def test_an_ARCHIVED_number_is_never_reissued(tmp_path, monkeypatch):
    """Closed work still owns its name — reissuing it makes every older cross-reference point at the wrong
    thing, silently."""
    inits = tmp_path / "initiatives"
    (inits / "archive").mkdir(parents=True)
    monkeypatch.setattr(I, "INITIATIVES", inits)
    (inits / "archive" / "V2-050-uc-cerrado.md").write_text("cerrado")
    got, _ = I.claim_initiative("nuevo")
    assert got > 50
