"""nucleo/mem_cli.py — MEMORY BRIDGE for SlowBrain Claude Code agents (V2-036).

It is the "independent and SERIAL component" with which a headless Claude Code agent USES zaelar's memory without
touching the DB directly (it preserves the SINGLE WRITER: it writes through the live process's queue). The agent
invokes it through Bash:

    python -m nucleo.mem_cli recall "moto de enduro del operador"        # REQUESTS a fact → prints the pills
    python -m nucleo.mem_cli remember "el operador quiere una KTM 350" --slot goal.moto   # SAVES a fact

It communicates with the local server (http://localhost:43917, ZAELAR_BASE override) over HTTP — it NEVER opens the
SQLite database in parallel, so the live process's "single writer" invariant is maintained. Serial by nature: one
call, one result, and the agent continues its execution. Fail-soft: if the server does not respond, it prints the
error and exits !=0 (the agent handles it).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")
_UA = "zaelar-mem-cli/1.0"


def _post(path: str, payload: dict, timeout: float = 20.0) -> dict:
    headers = {"Content-Type": "application/json", "User-Agent": _UA}
    # Per-task AUTH (audit 2026-07-14): the worker authenticates ITS session with the token that dispatch placed in
    # the environment (§v2·D) — /api/memory/remember requires it (an arbitrary local process can no longer write memory).
    tid, tok = os.getenv("ZAELAR_TASK_ID", ""), os.getenv("ZAELAR_TASK_TOKEN", "")
    if tid:
        headers["X-Zaelar-Task"] = tid
    if tok:
        headers["X-Zaelar-Token"] = tok
    req = urllib.request.Request(
        _BASE + path, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        # THE REASON IS IN THE BODY, and `HTTPError` only carries the number. Measured on 2026-08-28: five attempts
        # by the worker to save operational findings —«Wallapop filtro que funciona: …max_sale_price=8000»,
        # «Milanuncios bloqueado por anti-bot», «coches.net da error persistente»— ended with «HTTP Error
        # 422: Unprocessable Entity» and nothing else. The server DOES say why («descartado por el gate de
        # precisión (<razón>)»), and the worker never got to read it: it retries or gives up blindly, and the finding
        # —which is precisely what prevents the next worker from repeating the work— is lost.
        try:
            detalle = json.loads(e.read().decode("utf-8") or "{}").get("detail") or ""
        except Exception:  # noqa: BLE001
            detalle = ""
        raise RuntimeError(f"HTTP {e.code}" + (f": {detalle}" if detalle else f": {e.reason}")) from None


def _recall(query: str, k: int = 8) -> int:
    if not query.strip():
        print("uso: mem_cli recall \"<consulta>\"", file=sys.stderr)
        return 2
    try:
        res = _post("/api/memory/recall", {"query": query, "k": k})
    except Exception as e:  # noqa: BLE001
        print(f"recall error: {e}", file=sys.stderr)
        return 1
    print(res.get("text") or "(sin recuerdos relevantes)")
    return 0


def _remember(text: str, slot: str = "", kind: str = "") -> int:
    if not text.strip():
        print("uso: mem_cli remember \"<dato>\" [--slot X] [--kind Y]", file=sys.stderr)
        return 2
    payload: dict = {"text": text}
    if slot:
        payload["slot"] = slot
    if kind:
        payload["kind"] = kind
    try:
        _post("/api/memory/remember", payload)
    except Exception as e:  # noqa: BLE001
        print(f"remember error: {e}", file=sys.stderr)
        return 1
    print("guardado" + (f" (slot={slot})" if slot else ""))
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="mem_cli", description="Puente de memoria de zaelar para agentes Claude Code")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("recall", help="pide recuerdos relevantes a una consulta")
    r.add_argument("query")
    r.add_argument("-k", type=int, default=8, help="nº máx de píldoras (1-20)")
    w = sub.add_parser("remember", help="guarda un dato en la memoria (escritor único)")
    w.add_argument("text")
    w.add_argument("--slot", default="", help="clave canónica para supersede/dedup (p.ej. goal.moto)")
    w.add_argument("--kind", default="", help="fact|pref|result|event|summary|profile")
    a = ap.parse_args(argv)
    if a.cmd == "recall":
        return _recall(a.query, a.k)
    if a.cmd == "remember":
        return _remember(a.text, a.slot, a.kind)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
