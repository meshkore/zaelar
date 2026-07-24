"""nucleo/mem_cli.py — PUENTE de MEMORIA para los agentes Claude Code del SlowBrain (V2-036).

Es la "pieza independiente y SERIAL" con la que un agente Claude Code headless USA la memoria de zaelar sin tocar la
BD directamente (preserva el ESCRITOR ÚNICO: escribe por la cola del proceso vivo). El agente la invoca por Bash:

    python -m nucleo.mem_cli recall "moto de enduro del operador"        # PIDE un dato → imprime las píldoras
    python -m nucleo.mem_cli remember "el operador quiere una KTM 350" --slot goal.moto   # GUARDA un dato

Habla con el server local (http://localhost:43917, override ZAELAR_BASE) por HTTP — NUNCA abre la SQLite en paralelo,
así el invariante "único escritor" del proceso vivo se mantiene. Serial por naturaleza: una llamada, un resultado, y
el agente sigue su ejecución. Fail-soft: si el server no responde, imprime el error y sale !=0 (el agente lo maneja).
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
    # AUTH por-tarea (auditoría 2026-07-14): el worker acredita SU sesión con el token que dispatch le puso en el
    # entorno (§v2·D) — /api/memory/remember lo exige (un proceso local cualquiera ya no puede escribir memoria).
    tid, tok = os.getenv("ZAELAR_TASK_ID", ""), os.getenv("ZAELAR_TASK_TOKEN", "")
    if tid:
        headers["X-Zaelar-Task"] = tid
    if tok:
        headers["X-Zaelar-Token"] = tok
    req = urllib.request.Request(
        _BASE + path, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


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
