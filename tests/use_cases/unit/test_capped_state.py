"""A case whose other half demands the user's own credential is NOT a failure, and it cannot stay in the loop.

Operator's rule (2026-08-20): "those tests would be marked as special use cases that require credentials and
we do not include them in our sweep". The reason is material, not a matter of taste: today the product does
not store user logins, and the route that does exist locally — open a browser, let the person authenticate,
keep the cookies — is exactly what a backend harness cannot simulate. Scoring them FAIL left permanently red
rows and fed the improvement loop with work nobody can ever close.

The REACHABLE half is still scored in full: finding the options and offering them is the completable case;
closing and paying is the capped part.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import status as S


def _r(sid: str, overall: int, mech: int = 4) -> dict:
    return {"scenario": sid, "tier": 1, "channel": "probe",
            "run": {"transcript": [], "mechanism_report": {}},
            "verdict": {"overall": overall, "veredicto": "x",
                        "scores": {"naturalidad": 5, "adaptacion": 5, "resultado": overall,
                                   "mecanismo": mech, "eficiencia": 4}}}


def test_a_credentialed_case_is_CAPPED_not_failed():
    """`book-hotel-night-known` needs an account and a card to close the booking: it can never be a PASS here,
    and calling it a FAIL is not fair either."""
    assert S._state(2, _r("book-hotel-night-known__es", 2)) == "CAPPED"


def test_and_still_CAPPED_when_it_behaves_perfectly():
    """The cap does not depend on the score: a capped 5 means "it got as far as anyone can get", not a pass."""
    assert S._state(5, _r("cancel-subscription-before-charge__es", 5)) == "CAPPED"


def test_a_completable_case_is_untouched():
    """Sensitivity: if the new state swallowed normal cases, the board would stop measuring the product."""
    assert S._state(5, _r("build-workout-tracker-widget", 5)) == "PASS"
    assert S._state(2, _r("build-workout-tracker-widget", 2)) == "FAIL"


def test_the_mechanism_gate_still_applies_to_completable_cases():
    assert S._state(4, _r("build-workout-tracker-widget", 4, mech=2)) == "FAIL"


def test_INFRA_still_wins_over_the_cap():
    """A harness that died measured nothing, and that holds for a capped case too: it stays INFRA, not capped."""
    r = _r("book-hotel-night-known__es", 2)
    r["run"]["crashed"] = True
    assert S._state(2, r) == "INFRA"


def test_the_board_excludes_capped_from_the_pass_fail_count(tmp_path, monkeypatch):
    """What the operator actually asked for: that they do not interfere. Checked in the board's own text."""
    monkeypatch.setattr(S, "LEDGER_PATH", tmp_path / "status.json")
    monkeypatch.setattr(S, "BOARD_PATH", tmp_path / "STATUS.md")
    S.record([_r("build-workout-tracker-widget", 5), _r("book-hotel-night-known__es", 2)], sandboxed=True)
    board = (tmp_path / "STATUS.md").read_text()
    assert "1 passing · 0 failing" in board, board[board.find("passing") - 60:board.find("passing") + 40]
    assert "scenarios we can actually finish" in board
    assert "1 🔒 capped" in board
    assert "book-hotel-night-known__es" in board
