"""The scrape bench — real listing pages read through `scrape.read`, against a hand-labelled floor (V2-846 F0).

    ./.venv/bin/python -m tests.scrape.live.bench [--only autoscout24,wallapop]

For each page of `tests/scrape/bank/pages.json`: the rung that got it, the extractor that read it, how many listings
came against the floor a person counted, the share of them with every required field, seconds. Run it HERE and on a
Fly Machine: the exit IP is the variable that decides the fetch rung. The report lands in `tests/runs/` (local). Paid
rungs (the unlocker) cost ~$0.0015 a page; the model maps a site once.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
BANK = ENGINE / "tests" / "scrape" / "bank" / "pages.json"


def score(page: dict, records: list[dict]) -> dict:
    """`{n, floor, met, complete}` — complete = share of records with every required field. Pure."""
    fields = page.get("fields") or []
    full = sum(1 for r in records if all(r.get(f) not in (None, "") for f in fields))
    return {"n": len(records), "floor": page["min"], "met": len(records) >= page["min"],
            "complete": round(full / len(records), 2) if records else 0.0}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    from search.health import _load_credentials
    _load_credentials()
    import scrape
    from scrape import hooks
    from nucleo.memory_agent.processor import llm
    hooks.model = lambda system, user: llm.chat_sync("triage", system, user, max_tokens=500, timeout=40)
    pages = json.loads(BANK.read_text(encoding="utf-8"))["pages"]
    only = {s for s in a.only.split(",") if s}
    rows = []
    for page in pages:
        if only and page["site"] not in only:
            continue
        t = time.time()
        res = scrape.read(page["url"])
        row = {"site": page["site"], "how": res.how or "-", "extractor": res.extractor or "-",
               "s": round(time.time() - t, 1), "tried": res.tried, **score(page, res.records)}
        rows.append(row)
        print(f"{row['site']:14s} {row['how']:9s} {row['extractor']:13s} {row['n']:3d}/{row['floor']:<3d} "
              f"{'✓' if row['met'] else '✗'} complete {row['complete']:.2f}  {row['s']:5.1f}s  "
              + " ".join(f"{x['rung']}:{x['status']}" for x in res.tried), flush=True)
    met = sum(r["met"] for r in rows)
    print(f"\n{met}/{len(rows)} pages met their floor")
    out = ENGINE / "tests" / "runs" / f"scrape-bench-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), "rows": rows}, ensure_ascii=False, indent=1))
    print(f"report: {out}")


if __name__ == "__main__":
    main()
