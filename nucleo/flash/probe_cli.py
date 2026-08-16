"""nucleo/flash/probe_cli.py — CLI for the FlashBrain probe channel (V2-098 split).

Extracted from nucleo/flash/probe.py: this talks to the running server over plain HTTP (`_post`) and has no
access to, or need for, any of probe.py's in-process state (`run_turn`/`ProbeSession`/`_SESSIONS`) — a clean
boundary, unlike the HTTP router (`probe_api.py`), which does need that state and stays a thin wrapper around it.
`python -m nucleo.flash.probe` keeps working: probe.py's own `__main__` block delegates to `main()` here.
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
    # TOTALIZADORES (premisa de observabilidad): TTFT + tamaño de entrada/salida + cold, para distinguir «lento por
    # el modelo» de «lento por prompt gigante» o «frío».
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
    ap = argparse.ArgumentParser(description="Canal de prueba headless del FlashBrain")
    ap.add_argument("text", nargs="*", help="texto a inyectar (vacío = REPL)")
    ap.add_argument("--session", default="default")
    ap.add_argument("--base", default="http://localhost:43917")
    ap.add_argument("--no-ingest", action="store_true", help="no escribir a memoria (charla aislada)")
    ap.add_argument("--reset", action="store_true", help="limpia la ventana del probe y sale")
    ap.add_argument("--json", action="store_true", help="imprime el JSON completo")
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
    print("FlashBrain probe — escribe y pulsa enter (Ctrl-D para salir). `/reset` limpia la ventana.")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        if line == "/reset":
            print(_post("/api/flash/reset", {"session": args.session}, args.base))
            continue
        _send(line)
