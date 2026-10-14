"""`python -m tests.brain.runner` — the whole bank, one number per axis (V2-776 A1/A2).

    ./.venv/bin/python -m tests.brain.runner                # every case, a table and the four numbers
    ./.venv/bin/python -m tests.brain.runner --case <id>    # one case, its raw outcome
    ./.venv/bin/python -m tests.brain.runner --json out.json
    ./.venv/bin/python -m tests.brain.runner --live --repeat 7 --only demo-   # the real model and Jev, N times each

LIVE + REPEAT is the operator's guarantee (2026-10-15): «si siete veces se pide un dato, esas siete veces me venga».
The recorded bank says what the engine DECIDES given a model's words; it cannot say how often the model gives them.
Live, each case runs N times on the real fast model and the real brief, still isolated and with `execute=False`, and
counts only when it decides right N of N. It costs model calls, so it is a measurement you run, not a CI gate.

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


def run_repeated(cases: list[dict], times: int) -> tuple[list[dict], dict]:
    """Each case `times` times, live. A case holds only at N of N; the spread of decisions says where it wanders."""
    rows = []
    for case in cases:
        got, why, ms = [], [], []
        for _ in range(times):
            out = harness.run_case(case, live=True)
            got.append(out.decision or (f"(none: {out.error[:60]})" if out.error else "(none)"))
            why.append(out.failures(case))
            ms.append(out.ms)
        ok = sum(1 for w in why if not w)
        rows.append({"id": case["id"], "phrase": case["phrase"], "expect": case["expect"], "ok": ok, "times": times,
                     "decisions": {d: got.count(d) for d in dict.fromkeys(got)}, "why": [w for w in why if w][:3],
                     "ms_median": sorted(ms)[len(ms) // 2] if ms else 0})
    held = [r["id"] for r in rows if r["ok"] == r["times"]]
    return rows, {"cases": len(rows), "times": times, "held": len(held),
                  "wandering": [f"{r['id']} {r['ok']}/{r['times']}" for r in rows if r["ok"] < r["times"]]}


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
    ap.add_argument("--live", action="store_true", help="the real fast model and Jev instead of the recorded ones")
    ap.add_argument("--repeat", type=int, default=7, help="with --live: runs per case (a case holds only at N of N)")
    ap.add_argument("--only", help="case ids starting with this prefix")
    args = ap.parse_args(argv)
    cases = harness.load_cases()
    if args.only:
        cases = [c for c in cases if c["id"].startswith(args.only)]
    if args.case:
        cases = [c for c in cases if c["id"] == args.case]
        if not cases:
            print(f"no case {args.case!r}", file=sys.stderr)
            return 2
    if args.live:
        rows, axes = run_repeated(cases, max(1, args.repeat))
        for r in rows:
            mark = "✅" if r["ok"] == r["times"] else "❌"
            print(f"{mark} {r['ok']}/{r['times']}  {r['id']:<58} {r['decisions']}", flush=True)
        print(json.dumps(axes, ensure_ascii=False, indent=2))
        if args.json:
            with open(args.json, "w", encoding="utf-8") as fh:
                json.dump({"axes": axes, "rows": rows}, fh, ensure_ascii=False, indent=2, default=str)
        return 0 if not axes["wandering"] else 1
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
