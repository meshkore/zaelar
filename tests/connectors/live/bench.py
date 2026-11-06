"""The connectors bench — mail and Telegram through the engine's own card door, against the operator's test accounts
(V2-856). Numbers, not a conversation: what each step returned and how long it took.

    ./.venv/bin/python -m tests.connectors.live.bench                 # read · search · summarise (no message leaves)
    ./.venv/bin/python -m tests.connectors.live.bench --send          # + one marked message to each test contact,
                                                                      #   and the read-back that proves it left

It talks to a RUNNING engine (default the local one, `--url`) over `POST /widgets/mensajeria/action` — the door the
card's own buttons use — so it never opens a second Telegram session or reads a credential, and a sandbox cannot run
it on purpose (a sandbox never reaches his messaging accounts). The test contacts are PRIVATE and live outside the repo:
`.meshkore/credentials/bench_contacts.json` (gitignored) or the file named by `ZAELAR_BENCH_CONTACTS`:

    {"email":    {"source": "<a sender whose mail is in the inbox>", "to": "<the test address>"},
     "telegram": {"chat": "<the test contact's chat name>",           "to": "<the same contact>"}}

A platform with no entry is skipped and says so. `--send` writes ONLY to the `to` of that file, a marked line that
names the run — never to anyone the inbox suggests. The report lands in `tests/runs/connectors-bench-<stamp>.json`.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[3]
CONTACTS = ENGINE / ".meshkore" / "credentials" / "bench_contacts.json"
PLATFORMS = ("email", "telegram")
#: how long a sent line may take to show up in the archive before the step is a failure
DELIVERY_S = 90.0


def contacts(path: str | None = None) -> dict:
    p = Path(path or os.environ.get("ZAELAR_BENCH_CONTACTS") or CONTACTS)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in d.items() if k in PLATFORMS and isinstance(v, dict)}


def plan(platform: str, c: dict, *, send: bool, marker: str) -> list[tuple[str, str, dict]]:
    """The steps for one platform as (step, action, payload). Pure — the order is the bench's contract."""
    steps = [("fetch", "fetch_now", {"platform": platform, "since_hours": 72})]
    if platform == "email" and c.get("source"):
        steps.append(("search", "search_archive", {"platform": "email", "sender": c["source"]}))
    if platform == "telegram" and c.get("chat"):
        steps += [("read", "peek", {"name": c["chat"], "limit": 20}),
                  ("search", "search_archive", {"platform": "telegram", "chat": c["chat"]}),
                  ("summarise", "chat_digest", {"chat": c["chat"]})]
    if send and c.get("to"):
        steps.append(("send", "send_to", {"contact": c["to"], "channel": platform, "text": marker}))
    return steps


def score(step: str, res: dict) -> dict:
    """`{ok, n, why}` for one step's answer. Pure: an error, a refusal or an empty read is not a pass."""
    if not isinstance(res, dict) or res.get("error") or res.get("ok") is False:
        return {"ok": False, "n": 0, "why": str((res or {}).get("error") or (res or {}).get("message") or "refused")[:160]}
    r = res.get("result") or {}
    if step == "fetch":
        return {"ok": bool(r.get("asked")), "n": 0, "why": "" if r.get("asked") else "the connector was not asked"}
    if step == "read":
        n = int(r.get("returned") or 0)
        return {"ok": n > 0, "n": n, "why": "" if n else "the chat came back empty"}
    if step == "search":
        n = int(r.get("count") or 0)
        return {"ok": n > 0, "n": n, "why": "" if n else str(r.get("detail") or "no match")[:160]}
    if step == "summarise":
        d = (r.get("digests") or [{}])[0] if r.get("digests") else {}
        n = len(str(d.get("summary") or ""))
        return {"ok": n > 0, "n": n, "why": "" if n else str(r.get("detail") or "no digest")[:160]}
    if step == "send" and res.get("held"):
        return {"ok": False, "n": 0, "why": "held for his yes — the card's door asked for consent instead of sending"}
    if step == "send":
        return {"ok": bool(r.get("to")), "n": 1 if r.get("to") else 0, "why": "" if r.get("to") else "no recipient resolved"}
    if step == "delivered":
        n = int(r.get("count") or 0)
        return {"ok": n > 0, "n": n, "why": "" if n else f"the marked line was not in the archive after {DELIVERY_S:.0f} s"}
    return {"ok": False, "n": 0, "why": f"unknown step {step}"}


def _act(url: str, action: str, payload: dict, timeout: float = 60.0) -> dict:
    req = urllib.request.Request(f"{url.rstrip('/')}/widgets/mensajeria/action",
                                 data=json.dumps({"action": action, "payload": payload}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001 — a dead engine is a row of the report, not a traceback
        return {"error": f"{type(e).__name__}: {e}"[:160]}


def _delivered(url: str, platform: str, marker: str) -> tuple[dict, float]:
    t0 = time.time()
    res: dict = {}
    while time.time() - t0 < DELIVERY_S:
        res = _act(url, "search_archive", {"platform": platform, "q": marker, "direction": "out"})
        if int(((res or {}).get("result") or {}).get("count") or 0):
            break
        time.sleep(5)
    return res, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=os.environ.get("ZAELAR_URL", "http://127.0.0.1:43917"))
    ap.add_argument("--send", action="store_true", help="also send one marked line to each test contact")
    ap.add_argument("--only", default="", help="email,telegram")
    ap.add_argument("--contacts", default=None)
    a = ap.parse_args()
    book = contacts(a.contacts)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    marker = f"zaelar bench {stamp}"
    only = {p for p in a.only.split(",") if p} or set(PLATFORMS)
    rows = []
    for platform in PLATFORMS:
        if platform not in only:
            continue
        c = book.get(platform)
        if not c:
            rows.append({"platform": platform, "step": "-", "ok": None, "n": 0, "s": 0,
                         "why": "no test contact in the private contacts file — skipped"})
            print(f"{platform:9s} skipped: no test contact")
            continue
        for step, action, payload in plan(platform, c, send=a.send, marker=marker):
            t = time.time()
            res = _act(a.url, action, payload)
            row = {"platform": platform, "step": step, "action": action, "s": round(time.time() - t, 2), **score(step, res)}
            rows.append(row)
            print(f"{platform:9s} {step:10s} {'✓' if row['ok'] else '✗'} n={row['n']:<4d} {row['s']:6.2f}s  {row['why']}", flush=True)
            if step == "send" and row["ok"]:
                res, waited = _delivered(a.url, platform, marker)
                row = {"platform": platform, "step": "delivered", "action": "search_archive", "s": round(waited, 1),
                       **score("delivered", res)}
                rows.append(row)
                print(f"{platform:9s} {'delivered':10s} {'✓' if row['ok'] else '✗'} {row['s']:6.1f}s  {row['why']}", flush=True)
    measured = [r for r in rows if r["ok"] is not None]
    ok = sum(1 for r in measured if r["ok"])
    print(f"\n{ok}/{len(measured)} steps ok" + (" · nothing was sent (pass --send)" if not a.send else ""))
    out = ENGINE / "tests" / "runs" / f"connectors-bench-{stamp}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), "url": a.url, "sent": a.send, "rows": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"report: {out}")
    return 0 if ok == len(measured) else 1


if __name__ == "__main__":
    raise SystemExit(main())
