"""Terminal client of the typed channel: `python -m nucleo.cli "a line"` (or no argument for a REPL).

It talks to a running engine over HTTP (`POST /api/flash/say`, `nucleo/cli/api.py`) and holds no state of its own.
Moved from `nucleo/flash/probe_cli.py` with the text channel's own turn (refactor2710-01).
"""
from __future__ import annotations


def _post(path: str, payload: dict, base: str) -> dict:
    import json
    import urllib.request
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def _fmt(res: dict) -> str:
    if not res.get("ok"):
        return f"✗ {res.get('error', 'error')}"
    t = res.get("timings", {})
    extra = []
    if res.get("action") != "chat":
        extra.append(f"acción={res['action']}")
    if res.get("degenerate"):
        extra.append("⚠️DEGENERADO(saneado)")
    if res.get("loop_run", 0) >= 2:
        extra.append(f"⚠️BUCLE×{res['loop_run']}")
    tail = ("  [" + " · ".join(extra) + "]") if extra else ""
    # TOTALS (observability premise): TTFT + input/output size + cold, to distinguish “slow because of the model”
    # from “slow because of a huge prompt” or “cold”.
    m = res.get("metrics", {}) or {}
    ptok = m.get("prompt_tokens", m.get("prompt_tokens_est"))
    ctok = m.get("completion_tokens", m.get("completion_tokens_est"))
    cold = "❄️FRÍO" if m.get("cold_estimate") else "🔥"
    meta = (f"ttft={t.get('ttft_ms', '?')}ms · total={t.get('total_ms', '?')}ms · "
            f"in≈{ptok}tok/{m.get('prompt_chars', '?')}ch (+{m.get('n_tools', '?')}tools) · "
            f"out≈{ctok}tok · {cold}")
    return f"zaelar ▸ {res.get('reply', '')}{tail}\n         └ {meta}"


def main() -> None:
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="FlashBrain headless test channel")
    ap.add_argument("text", nargs="*", help="text to inject (empty = REPL)")
    ap.add_argument("--session", default="default")
    ap.add_argument("--base", default="http://localhost:43917")
    ap.add_argument("--no-ingest", action="store_true", help="do not write to memory (isolated conversation)")
    ap.add_argument("--reset", action="store_true", help="clear the probe window and exit")
    ap.add_argument("--json", action="store_true", help="print the complete JSON")
    args = ap.parse_args()

    if args.reset:
        print(_post("/api/flash/reset", {"session": args.session}, args.base))
        return

    def _send(txt: str) -> None:
        import json
        res = _post("/api/flash/say",
                    {"text": txt, "session": args.session, "ingest": not args.no_ingest}, args.base)
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else _fmt(res))

    if args.text:
        _send(" ".join(args.text))
        return
    print("FlashBrain probe — type and press Enter (Ctrl-D to exit). `/reset` clears the window.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "/reset":
            print(_post("/api/flash/reset", {"session": args.session}, args.base))
            continue
        _send(line)
