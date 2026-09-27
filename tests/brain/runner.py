"""`python -m tests.brain.runner` — the whole bank, one number per axis (V2-776 A1/A2).

    ./.venv/bin/python -m tests.brain.runner                # every case, a table and the four numbers
    ./.venv/bin/python -m tests.brain.runner --case <id>    # one case, its raw outcome
    ./.venv/bin/python -m tests.brain.runner --json out.json

The four axes the control run publishes (A2): routed-right %, false workers, wrong card, unanswered. A case
marked `open` counts in its own column and never in the exit code — the exit code is about REGRESSIONS:
non-zero when a case that was green is red.
"""
from __future__ import annotations

import argparse
import json
import sys

from tests.brain import harness


def _axes(rows: list[dict]) -> dict:
    live = [r for r in rows if not r["open"]]
    right = sum(1 for r in live if r["ok"])
    return {
        "cases": len(rows),
        "open": sum(1 for r in rows if r["open"]),
        "routed_right_pct": round(100.0 * right / max(1, len(live)), 1),
        "false_workers": sum(1 for r in live if "escalate" in r["all"] and "escalate" not in (r["expect"], *r["also_expected"])),
        "wrong_card": sum(1 for r in live if not r["ok"] and _card(r["decision"]) and _card(r["expect"])
                          and _card(r["decision"]) != _card(r["expect"])),
        "unanswered": sum(1 for r in live if not r["ok"] and (r["error"] or not r["decision"])),
        "regressions": [r["id"] for r in live if not r["ok"]],
        "still_open": [r["id"] for r in rows if r["open"] and not r["ok"]],
        "open_now_green": [r["id"] for r in rows if r["open"] and r["ok"]],
    }


def _card(decision: str) -> str:
    if decision.startswith(("show ", "close ", "data-op ", "read ")):
        return decision.split(" ", 1)[1].split(":", 1)[0]
    return ""


def run(cases: list[dict]) -> tuple[list[dict], dict]:
    rows = []
    for case in cases:
        out = harness.run_case(case)
        why = out.failures(case)
        rows.append({"id": case["id"], "lang": case["lang"], "phrase": case["phrase"], "expect": case["expect"],
                     "also_expected": list(case.get("also", ())), "decision": out.decision, "all": out.all_decisions,
                     "ok": not why, "why": why, "open": case.get("open", ""), "error": out.error,
                     "ms": round(out.ms, 1), "outcome": out.as_dict()})
    return rows, _axes(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="the decision bank")
    ap.add_argument("--case", help="one case id")
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args(argv)
    cases = harness.load_cases()
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"no case {args.case!r}", file=sys.stderr)
            return 2
    rows, axes = run(cases)
    for r in rows:
        mark = "✅" if r["ok"] else ("🟡" if r["open"] else "❌")
        print(f"{mark} {r['id']:<58} {r['decision']:<32} {r['ms']:>7.0f} ms")
        for w in r["why"]:
            print(f"      · {w}")
    print()
    print(json.dumps(axes, ensure_ascii=False, indent=2))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"axes": axes, "rows": rows}, fh, ensure_ascii=False, indent=2, default=str)
    return 1 if axes["regressions"] or axes["open_now_green"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
