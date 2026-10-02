"""When is a use case's result SETTLED, and when has it gone STALE? (V2-779 F2)

Two holes the 2026-10-02 diagnosis measured in the scoreboard:

- **One round is not a measurement.** The driver runs at temperature 0.7 and the judge chain falls back across
  vendors, so the same code can score 2 and 4 on consecutive rounds. `--rounds N` existed, but `status.record`
  OVERWROTE the row each time: only the last round survived, and a lucky one read as PASS. A row now keeps its
  recent rounds, and a case is settled only when the last `K` rounds on the SAME code agree — `k/k`.
- **A result has a subject, and the subject moves.** 66 of the 72 rows were older than 09-03; the board showed
  them as current. A row is STALE when product code changed between the commit it measured and HEAD. Changes
  under `tests/`, `.meshkore/` or to Markdown do not count: the harness and the diary are not the product.

Pure data over the ledger row — no engine, no model — so every rule here has a deterministic test.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[4]

#: Rounds kept per row. Enough for k/k at K=3 with room for a flaky streak to be SEEN, small enough that the
#: committed ledger does not become a diary (it is public: scores and states only, never what was said).
ROUNDS_KEPT = 8
#: Rounds that must agree, on the same code, for a case to be settled.
K = 3

#: Paths whose change does not change the product under test.
_NOT_PRODUCT = ("tests/", ".meshkore/", ".github/", ".claude/")


def round_of(entry: dict) -> dict:
    """The compact, public shape of one round: what was decided, by which ruler, on which code."""
    code = entry.get("code") or {}
    return {
        "at": entry.get("last_run"),
        "state": entry.get("state"),
        "overall": entry.get("overall"),
        "judge": entry.get("judge") or "",
        "sha": code.get("sha") or "",
        # A round on a dirty tree or flagged provisional is evidence, not a measurement — kept, never counted.
        "counted": bool(code.get("sha")) and not code.get("n_dirty") and not entry.get("provisional"),
    }


def fold(prior: dict | None, entry: dict) -> dict:
    """`entry` with its round appended to the prior row's history. A row written before this existed carries
    no history; its own last round is folded in first so nothing measured is forgotten."""
    history = list((prior or {}).get("rounds") or [])
    if prior and not history and prior.get("last_run"):
        history.append(round_of(prior))
    history.append(round_of(entry))
    entry["rounds"] = history[-ROUNDS_KEPT:]
    return entry


def kk(entry: dict, k: int = K) -> dict:
    """The settled verdict of a row: `{"n": rounds counted on the latest code, "pass": …, "settled": …}`.

    `settled` is `PASS` / `FAIL` only when the last `k` counted rounds on the latest measured sha all say so;
    `FLAKY` when they disagree; `UNSETTLED` with fewer than `k`. INFRA and CAPPED rounds are not a verdict on
    the product and are skipped, never counted as a pass or a fail.
    """
    rounds = [r for r in (entry.get("rounds") or []) if r.get("counted")]
    if not rounds:
        return {"n": 0, "pass": 0, "settled": "UNSETTLED"}
    sha = rounds[-1]["sha"]
    same = [r for r in rounds if r["sha"] == sha and r.get("state") in ("PASS", "FAIL")]
    last = same[-k:]
    n_pass = sum(1 for r in last if r["state"] == "PASS")
    if len(last) < k:
        settled = "UNSETTLED"
    elif n_pass == k:
        settled = "PASS"
    elif n_pass == 0:
        settled = "FAIL"
    else:
        settled = "FLAKY"
    return {"n": len(last), "pass": n_pass, "settled": settled}


def _git(*args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(["git", *args], cwd=str(ENGINE), capture_output=True, text=True, timeout=30)
    except Exception:                                    # noqa: BLE001 — no git means we cannot say it is fresh
        return 1, ""
    return done.returncode, done.stdout


@lru_cache(maxsize=256)
def product_changed_since(sha: str, head: str = "HEAD") -> list[str] | None:
    """Product paths changed between `sha` and `head`, or None when `sha` is not a commit this checkout knows
    (a rewritten history, a shallow clone) — which the caller must read as STALE, never as fresh."""
    if not sha:
        return None
    code, out = _git("diff", "--name-only", f"{sha}..{head}", "--")
    if code != 0:
        return None
    return [p for p in out.splitlines()
            if p.strip() and not p.startswith(_NOT_PRODUCT) and not p.endswith(".md")]


def stale(entry: dict, head: str = "HEAD") -> bool:
    """True when the code this row measured is not the code at `head` any more (product paths only)."""
    changed = product_changed_since(((entry.get("code") or {}).get("sha") or ""), head)
    return changed is None or bool(changed)
