"""nucleo/agent_report.py — `hbnote`: CLI de REPORTE para los workers Claude Code (V2-036 · plan/progreso V2-059).

Un agente Claude Code headless lo invoca por Bash para contarle al FlashBrain qué está haciendo, para que el
operador lo vea SIN esperar al final. Observabilidad ESTRUCTURADA (V2-059): además de la fase legible, el worker
DECLARA su plan y REPORTA su progreso → el registro sabe en qué paso va y a qué % → lo ve el FlashBrain (para
responder "¿cómo va?"), la UI (progreso) y el debug.

    python -m nucleo.agent_report phase    "navegando a Wallapop y filtrando por enduro"
    python -m nucleo.agent_report note     "he descartado 4 anuncios de trial"
    python -m nucleo.agent_report plan      "leer la spec|editar data.py|reescribir widget.js|validar"
    python -m nucleo.agent_report progress  "widget.js reescrito" --done 3
    python -m nucleo.agent_report progress  "compilando"        --pct 80

El id de la sesión sale del entorno `ZAELAR_TASK_ID` (lo inyecta el dispatcher al lanzar el agente) → el agente no
tiene que conocerlo. Habla por HTTP con el server vivo (ZAELAR_BASE, def localhost:43917). Fail-soft.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")


def _post(payload: dict) -> int:
    tid = os.getenv("ZAELAR_TASK_ID", "").strip()
    if not tid:
        print("ZAELAR_TASK_ID no definido (no soy un worker gestionado) — ignoro", file=sys.stderr)
        return 0
    payload = {"tid": tid, **payload}
    try:
        req = urllib.request.Request(
            _BASE + "/api/agent/report", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "zaelar-hbnote/1.0"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"report error: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="agent_report", description="Reporte de progreso del worker al FlashBrain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("phase", help="actualiza la fase legible de la sesión (visible para el operador)")
    p.add_argument("text")
    n = sub.add_parser("note", help="deja una traza en observabilidad")
    n.add_argument("text")
    pl = sub.add_parser("plan", help="declara la LISTA DE TAREAS al empezar (pasos separados por | )")
    pl.add_argument("text")
    pr = sub.add_parser("progress", help="reporta progreso: nota + --done N (pasos hechos) y/o --pct P (0-100)")
    pr.add_argument("text", nargs="?", default="")
    pr.add_argument("--done", type=int, default=None)
    pr.add_argument("--pct", type=int, default=None)
    co = sub.add_parser("considered", help="AMPLITUD: cuántos candidatos has evaluado de verdad (--kept N finalistas)")
    co.add_argument("n", type=int)
    co.add_argument("--kept", type=int, default=None)
    a = ap.parse_args(argv)
    if a.cmd == "phase":
        return _post({"phase": a.text})
    if a.cmd == "note":
        return _post({"note": a.text})
    if a.cmd == "plan":
        return _post({"plan": a.text})
    if a.cmd == "progress":
        body: dict = {"progress": a.text or ""}
        if a.done is not None:
            body["done"] = a.done
        if a.pct is not None:
            body["pct"] = a.pct
        return _post(body)
    if a.cmd == "considered":
        body = {"considered": a.n}
        if a.kept is not None:
            body["kept"] = a.kept
        return _post(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
