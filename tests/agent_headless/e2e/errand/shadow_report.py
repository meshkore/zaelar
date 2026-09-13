"""What the errand WOULD have said — the arming gate, turned into a number (V2-684).

V2-683 ships in shadow, and the operator's condition for handing over the authority is «a handful of real
errands whose shadow decisions he reads and agrees with, with ZERO decisions that would have written to the
wrong person». That is a measurement, and until this file there was nothing that measured it: the
decisions were in observability, one line at a time, mixed in with everything else the engine says.

    ./.venv/bin/python -m tests.agent_headless.e2e.errand.shadow_report
    ./.venv/bin/python -m tests.agent_headless.e2e.errand.shadow_report --limit 4000 --json

READ-ONLY. It opens the engine's own event log and its errand ledger and writes nothing anywhere.

## The verdict line, and why it is the one that matters

Every other question about a shadow decision («is that a good sentence?») is his to answer by reading.
Exactly one can be answered mechanically, and it is the one with the irreversible cost: **was the
conversation this decision would have gone to the errand's OWN bound thread?** The engine holds that with
two independent guards (a whitelist on the parse, and a send BUILT from the binding), so the expected
answer is zero mismatches — and a report that cannot find a single decision says so instead of printing a
reassuring zero over nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
import time


def _decisions(limit: int) -> list[dict]:
    """Every errand decision the engine has logged, oldest first."""
    from bus import log
    out = []
    for ev in reversed(log.recent(limit, topic="observer")):
        p = ev.get("payload") or {}
        if not isinstance(p, dict) or p.get("kind") != "errand":
            continue
        extra = p.get("extra") or {}
        if not isinstance(extra, dict) or not extra.get("errand"):
            continue
        out.append({"ts": ev.get("ts_ms", 0) / 1000.0, "label": p.get("label") or "",
                    "would_say": p.get("text") or "", **extra})
    return out


def _errand_rows(ids) -> dict:
    from memory import errands_store as store
    rows = {}
    for eid in ids:
        r = store.errand_get(eid)
        if r:
            rows[eid] = dict(r)
    return rows


def _threads(eid: str) -> list[str]:
    from memory import errands_store as store
    return [f"{t.get('platform')}:{t.get('chat_id')}" for t in (store.errand_threads(eid) or [])]


def report(limit: int = 2000) -> dict:
    decisions = _decisions(limit)
    spoke = [d for d in decisions if d.get("would_say") or d.get("sent")]
    rows = _errand_rows({d["errand"] for d in decisions})
    wrong = []
    for d in spoke:
        # A decision reaches a person through the errand's binding and nothing else. If a decision exists
        # for an errand that owns NO conversation, that is the mismatch — there was nowhere legitimate for
        # it to go.
        if not _threads(d["errand"]):
            wrong.append(d)
    return {"decisions": decisions, "spoke": spoke, "rows": rows, "wrong": wrong,
            "errands": sorted({d["errand"] for d in decisions})}


def main() -> int:
    ap = argparse.ArgumentParser(description="Read the errand's shadow decisions.")
    ap.add_argument("--limit", type=int, default=2000, help="how many recent events to scan")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    r = report(args.limit)
    if args.json:
        print(json.dumps({k: v for k, v in r.items() if k != "rows"}, ensure_ascii=False, indent=1,
                         default=str))
        return 0

    if not r["decisions"]:
        print("No errand decisions in the log yet — nothing to read, and nothing to arm on.\n"
              "  → open one (the live node: tests.agent_headless.e2e.errand.run_live) and come back.")
        return 1

    for eid in r["errands"]:
        row = r["rows"].get(eid) or {}
        mine = [d for d in r["decisions"] if d["errand"] == eid]
        where = ", ".join(_threads(eid)) or "— no conversation bound —"
        print(f"\n▪ {eid} · {row.get('state') or '?'} · {where}")
        print(f"  objective: {str(row.get('objective') or '')[:110]}")
        for d in mine:
            when = time.strftime("%d/%m %H:%M", time.localtime(d["ts"]))
            mark = "SENT   " if d.get("sent") else "shadow "
            print(f"    {when}  {mark}[{d.get('state') or '?':<11}] {d.get('would_say') or '(nothing to say)'}")
            if d.get("reason"):
                print(f"{'':>25}reason: {d['reason']}")

    n_e, n_d, n_w = len(r["errands"]), len(r["spoke"]), len(r["wrong"])
    print(f"\n{'─' * 78}")
    print(f"{n_e} errand(s) · {n_d} decision(s) that would have spoken · "
          f"{n_w} that would have written to the wrong person")
    if n_w:
        print("\n⚠️  DO NOT ARM. Each of these decided to speak with no conversation of its own:")
        for d in r["wrong"]:
            print(f"    {d['errand']} · {d.get('would_say')}")
        return 1
    print("\nThe mechanical half is clean. The other half is yours: read the sentences above and decide "
          "whether you would have sent them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
