"""Reading the highest number does NOT avoid the collision, and this is measured: T448, T454 and T457 all
came out duplicated on the same day (2026-08-20), each one repaired by hand.

The window is the one between "look up the last number" and "write the file": both sides look, both get the
same number, and only afterwards do they write. And a duplicated number is not a cosmetic mess — two files
share an `id`, so the tick's resolver can pick the wrong one and re-measure a case nobody asked for.

`claim_task` closes the window with `open(..., "x")`: the first caller keeps the name, the second gets
FileExistsError and moves on to the next number.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import initiative as I


def test_two_claims_in_a_row_never_share_a_number(tmp_path):
    n1, p1 = I.claim_task(tmp_path / "tasks", "uc-case-fix")
    n2, p2 = I.claim_task(tmp_path / "tasks", "uc-case-fix")
    assert n1 != n2, "two consecutive claims took the same number"
    assert p1 != p2 and p1.exists() and p2.exists()


def test_the_file_exists_the_INSTANT_the_number_is_handed_out(tmp_path):
    """The whole point: the number comes with the file already created. If only the number came back, the
    window would stay open until somebody wrote."""
    n, p = I.claim_task(tmp_path / "tasks", "uc-case-fix")
    assert p.exists(), "the number was handed out without reserving the file: the race is still open"
    assert p.name == f"T{n}-uc-case-fix.md"


def test_a_name_already_taken_by_SOMEONE_ELSE_is_skipped(tmp_path):
    """Simulates the other agent: the name we would get is already taken, and it must be skipped rather than
    overwritten."""
    tasks = tmp_path / "tasks"
    tasks.mkdir(parents=True)
    n = I._next_task_number()
    (tasks / f"T{n}-uc-case-fix.md").write_text("from the other agent")
    got, path = I.claim_task(tasks, "uc-case-fix")
    assert got > n
    assert (tasks / f"T{n}-uc-case-fix.md").read_text() == "from the other agent", "we overwrote their task"


def test_it_creates_the_folder_if_it_is_a_new_module(tmp_path):
    n, p = I.claim_task(tmp_path / "new-module" / "tasks", "uc-case-fix")
    assert p.exists()
