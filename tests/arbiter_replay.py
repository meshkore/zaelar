"""Replay the canvas arbiter over an observer archive, and judge every veto against the turn's own verdict.

    ./.venv/bin/python -m tests.arbiter_replay <archive-dir> [--md out.md]

An archive is a folder of session event logs (`*.jsonl`, one observer event per line, the shape the Master exports).
Every `widget` mutation is fed, in event-time order, to `nucleo.canvas_arbiter.decide()` with the context the live
shadow tap assembles (the operator's last turn within 25 s, the ambient credit, our last reply), plus the cards open
before it and the turn's brief verdict (`jev read canvas|screen_action|catalog_widget`, joined by `trace`).

A veto is classed against that verdict: FALSE when the verdict ordered exactly this act (≥ 0.5), TRUE when the operator
undid it by hand within 60 s or the verdict said otherwise at ≥ 0.85, CONFLICT when `canvas=neither` was sure while
`catalog_widget` named the card, REPORT for a canvas report (`client` with no cause), UNKNOWN-SRC for a provenance the
tree has no branch for, UNDETERMINED otherwise. The report holds ids, traces, rules and counts — never operator text.
The promotion gate of the arbiter is FALSE == 0.
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import os

KEYS = ("canvas", "screen_action", "catalog_widget")
TTL_MS = 25_000
UNDO_MS = 60_000
CLASSES = ("FALSE", "TRUE", "CONFLICT", "REPORT", "UNKNOWN-SRC", "UNDETERMINED")


def _events(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                e = json.loads(line)
                p = json.loads(e.get("payload") or "{}")
            except (ValueError, TypeError):
                continue
            p.setdefault("kind", e.get("kind"))
            p.setdefault("label", e.get("label"))
            p["_t"] = float(p.get("t_ms") or e.get("ts_ms") or 0)
            out.append(p)
    return sorted(out, key=lambda p: p["_t"])


def _op(p: dict) -> tuple[str, str]:
    label = str(p.get("label") or "")
    if label == "show":
        return "show", str(p.get("action") or "")
    if label == "close":
        return "close", ""
    if label.startswith("data:"):
        return "data", label.split(":", 1)[1]
    if label == "action":
        return "data", str(p.get("action") or "")
    return "", ""


def _klass(op: str, wid: str, action: str, src: str, verdict: dict, undone: bool) -> tuple[str, str]:
    from voice import canvas_src
    base = wid.split("::", 1)[0]
    canvas, ccf = verdict.get("canvas", ("", 0.0))
    target, tcf = verdict.get("screen_action", ("", 0.0))
    cat, kcf = verdict.get("catalog_widget", ("", 0.0))
    if op == "close" and canvas == "close" and ccf >= 0.5:
        return "FALSE", f"canvas=close {ccf:.2f}"
    if op == "show" and canvas == "show" and ccf >= 0.5:
        return "FALSE", f"canvas=show {ccf:.2f}"
    if op == "data" and target == f"{base}:{action}" and tcf >= 0.5:
        return "FALSE", f"screen_action={target} {tcf:.2f}"
    if undone:
        return "TRUE", "the operator undid it by hand within 60 s"
    if op == "show" and canvas == "neither" and ccf >= 0.85 and cat == base:
        return "CONFLICT", f"canvas=neither {ccf:.2f} vs catalog_widget={cat} {kcf:.2f}"
    if canvas and canvas != op and ccf >= 0.85:
        return "TRUE", f"canvas={canvas} {ccf:.2f}"
    if src == canvas_src.CLIENT:
        return "REPORT", "a canvas report with no cause (`client`)"
    if src.split(":", 1)[0] == "wall":
        return "UNKNOWN-SRC", "provenance `wall:<tid>`"
    shown = ", ".join(f"{k}={v[0] or '∅'} {v[1]:.2f}" for k, v in verdict.items()) or "no verdict on this trace"
    return "UNDETERMINED", shown


def _judge(arb, p: dict, op: str, action: str, ctx: dict) -> object:
    wid = str(p.get("id") or "").strip().lower()
    t = p["_t"]
    turn = ctx["turn"]
    text, credit = ((str(p.get("text") or ""), True) if op == "data" and p.get("text")
                    else ((turn["text"], turn["credit"]) if t - turn["t"] <= TTL_MS else ("", True)))
    kw = dict(action=action, payload=p.get("payload") if isinstance(p.get("payload"), dict) else {},
              text=text, turn_credit=credit, last_reply=turn["reply"], open_ids=tuple(ctx["open"]))
    if "verdict" in arb.decide.__code__.co_varnames:
        kw["verdict"] = ctx["verdict"]
    return arb.decide(op, wid, str(p.get("src") or "system"), **kw)


def _session(path: str, arb, rows: list, totals: collections.Counter, per: collections.Counter) -> None:
    sid = os.path.basename(path)[:8]
    evs = _events(path)
    ctx = {"turn": {"text": "", "t": 0.0, "credit": True, "reply": ""}, "open": [], "verdict": {}}
    reads: dict[str, dict] = collections.defaultdict(dict)
    for i, p in enumerate(evs):
        kind, label, turn = p.get("kind"), str(p.get("label") or ""), ctx["turn"]
        if kind == "transcript" and p.get("role") in ("user", "assistant"):
            if p["role"] == "user":
                turn.update(text=str(p.get("text") or ""), t=p["_t"], credit=True)
            else:
                turn["reply"] = str(p.get("text") or "")
            continue
        if kind == "ambient":
            turn["credit"] = False if "🙉" in label else (True if ("👂" in label or "dirigido" in label) else turn["credit"])
            continue
        if kind == "brain" and label.startswith("jev read ") and p.get("question") in KEYS and p.get("trace"):
            reads[p["trace"]][p["question"]] = (str(p.get("choice") or ""), float(p.get("confidence") or 0))
            continue
        op, action = _op(p) if kind == "widget" else ("", "")
        src = str(p.get("src") or "system")
        if not op or (label == "action" and src.split(":", 1)[0] == "flash") or src == "client:engine":
            continue
        wid = str(p.get("id") or "").strip().lower()
        ctx["verdict"] = dict(reads.get(str(p.get("trace") or ""), {}))
        v = _judge(arb, p, op, action, ctx)
        totals["judged"] += 1
        per[sid] += 1
        if op == "show" and wid not in ctx["open"]:
            ctx["open"].append(wid)
        elif op == "close":
            ctx["open"][:] = [w for w in ctx["open"] if w != wid]
        if v.allow:
            totals["allowed"] += 1
            continue
        undone = any(q.get("kind") == "widget" and str(q.get("src")) == "user" and str(q.get("id") or "").lower() == wid
                     and q["_t"] - p["_t"] <= UNDO_MS for q in evs[i + 1:i + 400])
        klass, why = _klass(op, wid, action, src, ctx["verdict"], undone)
        totals["vetoed"] += 1
        totals[klass] += 1
        rows.append({"class": klass, "session": sid, "trace": p.get("trace") or "—", "op": op, "card": wid,
                     "action": action or "—", "src": src, "rule": v.rule, "evidence": why})


def replay(folder: str) -> dict:
    from nucleo import canvas_arbiter as arb
    rows, totals, per = [], collections.Counter(), collections.Counter()
    for path in sorted(glob.glob(os.path.join(folder, "*.jsonl"))):
        _session(path, arb, rows, totals, per)
    return {"totals": dict(totals), "rows": rows, "sessions": len([s for s in per if per[s]])}


def markdown(res: dict) -> str:
    t = res["totals"]
    lines = ["| judged | allowed | vetoed | " + " | ".join(CLASSES) + " |", "|" + "---:|" * (3 + len(CLASSES)),
             f"| {t.get('judged', 0)} | {t.get('allowed', 0)} | {t.get('vetoed', 0)} | "
             + " | ".join(str(t.get(k, 0)) for k in CLASSES) + " |", "",
             "| class | session | turn | op | card | action | src | rule | evidence |",
             "|---|---|---|---|---|---|---|---|---|"]
    order = {k: i for i, k in enumerate(CLASSES)}
    for r in sorted(res["rows"], key=lambda r: (order[r["class"]], r["session"])):
        lines.append("| {class} | `{session}` | {trace} | {op} | {card} | {action} | `{src}` | `{rule}` | {evidence} |"
                     .format(**r))
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Replay the canvas arbiter over an observer archive.")
    ap.add_argument("archive")
    ap.add_argument("--md")
    a = ap.parse_args(argv)
    res = replay(a.archive)
    if a.md:
        with open(a.md, "w", encoding="utf-8") as fh:
            fh.write(markdown(res))
    print(json.dumps({**res["totals"], "sessions": res["sessions"]}, sort_keys=True))
    return 0 if not res["totals"].get("FALSE") else 1


if __name__ == "__main__":
    raise SystemExit(main())
