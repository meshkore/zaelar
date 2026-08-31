"""An ARCHIVED number remains yours forever.

Written on 2026-08-20, when archiving the board: 87 terminal initiatives and 210 tasks were moved to
`archive/`, and both number assigners searched with non-recursive `glob`. Without recursion, archiving the
highest initiative makes its number available again.

And the harm caused by reusing a number here is the expensive kind: nothing fails, nothing turns red. Two
unrelated pieces of history simply answer to the same name, and every cross-reference written BEFORE the
reuse—in a task, in a commit, in `CLAUDE.md`—silently starts pointing to the other one.

⚠️ These tests deliberately set up the board in a TEMPORARY directory. The first version asserted the
same thing against the real disk and passed with the broken `glob`: today all archived numbers are BELOW
the live maximum, so `max+1` skips them by accident and the test measured nothing. The dangerous situation
—the highest number living ONLY in `archive/`—is exactly what arrives when V2-201 is closed, and it must be
built, not awaited.
"""
from __future__ import annotations

import pytest

from tests.use_cases.e2e.agent import initiative as I


@pytest.fixture
def board(tmp_path, monkeypatch):
    """A board where the highest number ever used is ARCHIVED, not live."""
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
    """The sensitivity check: looking inside the archive must not cause the live board to be IGNORED."""
    (board / "initiatives" / "V2-300-mas-alta-y-viva.md").write_text("---\nstatus: open\n---\n")
    assert I._next_initiative_number() == 301
