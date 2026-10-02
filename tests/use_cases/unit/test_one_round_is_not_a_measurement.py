"""V2-779 F2 — a use case's verdict is k/k on the same code, and a verdict on old code says it is STALE.

Measured 2026-10-02: `--rounds N` overwrote the ledger row on every round, so only the last one survived and
a lucky round read as PASS; and 66 of 72 rows were older than 09-03 while the board showed them as current.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import settle
from tests.use_cases.e2e.agent import status as S


def _row(state, sha="abc1234", dirty=0, provisional=None, at="2026-10-02 10:00"):
    return {"state": state, "overall": 5 if state == "PASS" else 2, "judge": "glm-4.6", "last_run": at,
            "code": {"sha": sha, "n_dirty": dirty}, "provisional": provisional}


def _with_rounds(*states, sha="abc1234"):
    row: dict = {}
    for st in states:
        row = settle.fold(row or None, _row(st, sha=sha))
    return row


# ── k/k ────────────────────────────────────────────────────────────────────────────────────────────────

def test_three_passes_on_the_same_code_are_settled():
    assert settle.kk(_with_rounds("PASS", "PASS", "PASS"))["settled"] == "PASS"


def test_one_pass_is_not_settled():
    """The lucky round: before F2 this was the whole row."""
    assert settle.kk(_with_rounds("PASS"))["settled"] == "UNSETTLED"


def test_disagreeing_rounds_on_the_same_code_are_FLAKY_not_the_last_one():
    k = settle.kk(_with_rounds("FAIL", "PASS", "PASS"))
    assert k["settled"] == "FLAKY" and k["pass"] == 2


def test_rounds_on_older_code_do_not_count_toward_the_new_code():
    row = _with_rounds("PASS", "PASS", sha="old0001")
    row = settle.fold(row, _row("PASS", sha="new0002"))
    assert settle.kk(row) == {"n": 1, "pass": 1, "settled": "UNSETTLED"}


def test_infra_and_dirty_and_provisional_rounds_are_kept_but_never_counted():
    row = _with_rounds("PASS", "PASS")
    for extra in (_row("INFRA"), _row("FAIL", dirty=3), _row("FAIL", provisional="allow-dirty")):
        row = settle.fold(row, extra)
    assert len(row["rounds"]) == 5, "evidence is kept"
    assert settle.kk(row)["settled"] == "UNSETTLED", "…but two clean passes are still two"


def test_a_row_from_before_the_history_keeps_its_round():
    legacy = _row("FAIL")                       # a ledger row written before `rounds` existed
    row = settle.fold(legacy, _row("PASS"))
    assert [r["state"] for r in row["rounds"]] == ["FAIL", "PASS"]


def test_history_is_bounded():
    row = _with_rounds(*(["PASS"] * (settle.ROUNDS_KEPT + 4)))
    assert len(row["rounds"]) == settle.ROUNDS_KEPT


def test_record_APPENDS_the_round_instead_of_overwriting_it():
    """The defect itself, through the real writer (ledger redirected by the folder's conftest)."""
    def res(overall):
        return {"scenario": "x__es", "tier": 1, "verdict": {"overall": overall, "scores": {"mecanismo": 4},
                                                          "veredicto": "v"},
                "run": {"transcript": [], "mechanism_report": {}}}
    S.record([res(5)], sandboxed=True)
    led = S.record([res(2)], sandboxed=True)
    rounds = led["scenarios"]["x__es"]["rounds"]
    assert [r["overall"] for r in rounds] == [5, 2]


# ── STALE ──────────────────────────────────────────────────────────────────────────────────────────────

def test_a_row_on_HEAD_is_fresh():
    code, head = settle._git("rev-parse", "--short", "HEAD")
    assert code == 0
    assert not settle.stale({"code": {"sha": head.strip()}})


def test_an_unknown_commit_is_STALE_never_fresh():
    assert settle.stale({"code": {"sha": "deadbee"}})
    assert settle.stale({"code": {}})


def test_only_PRODUCT_changes_make_a_row_stale(monkeypatch):
    settle.product_changed_since.cache_clear()
    monkeypatch.setattr(settle, "_git", lambda *a: (0, "tests/x.py\n.meshkore/docs/a.md\nREADME.md\n"))
    assert not settle.stale({"code": {"sha": "aaaaaaa"}}), "harness, diary and docs are not the product"
    settle.product_changed_since.cache_clear()
    monkeypatch.setattr(settle, "_git", lambda *a: (0, "tests/x.py\nnucleo/flash/prompt.py\n"))
    assert settle.stale({"code": {"sha": "aaaaaaa"}})
    settle.product_changed_since.cache_clear()
