"""nucleo/cli/report.py — `hbnote`: CLI de REPORTE para los workers Claude Code (V2-036 · plan/progreso V2-059).

Un agente Claude Code headless lo invoca por Bash para contarle al FlashBrain qué está haciendo, para que el
operador lo vea SIN esperar al final. Observabilidad ESTRUCTURADA (V2-059): además de la fase legible, el worker
DECLARA su plan y REPORTA su progreso → el registro sabe en qué paso va y a qué % → lo ve el FlashBrain (para
responder "¿cómo va?"), la UI (progreso) y el debug.

    python -m nucleo.cli.report phase    "navegando a Wallapop y filtrando por enduro"
    python -m nucleo.cli.report note     "he descartado 4 anuncios de trial"
    python -m nucleo.cli.report plan      "leer la spec|editar data.py|reescribir widget.js|validar"
    python -m nucleo.cli.report progress  "widget.js reescrito" --done 3
    python -m nucleo.cli.report progress  "compilando"        --pct 80
    python -m nucleo.cli.report goal '{"all":[{"widget":"agenda","collection":"meetings","where":{"title~":"Cryptonite"},"expect":"absent"}]}'

DECLARA TU OBJETIVO AL EMPEZAR (`goal`). Es CÓMO SE MIDE que el encargo está hecho, leído contra la verdad
del propio producto cuando termines: si no se cumple, se te relanza UNA vez diciéndote qué falta, en vez de
entregar al operador algo a medias. Cerrado en OPERADORES, abierto en CONTENIDO — mira `nucleo/circuit/verify.py`.

El id de la sesión sale del entorno `ZAELAR_TASK_ID` (lo inyecta el dispatcher al lanzar el agente) → el agente no
tiene que conocerlo. Habla por HTTP con el server vivo (ZAELAR_BASE, def localhost:43917). Fail-soft.
"""
from __future__ import annotations

_GOAL_HELP = (
    "forma: {\"all\": [{\"widget\": \"agenda\", \"collection\": \"meetings\", "
    "\"where\": {\"title~\": \"Cryptonite\"}, \"expect\": \"present|absent\"}]}\n"
    "  · `where` es la misma expresión de `hbwidget rows`: campo · campo~ (contiene) · campo>= <= > < · campo!\n"
    "  · «all» exige todas; «any» con una basta; `count` admite un número o {\"min\": n, \"max\": m}\n"
    "  · las colecciones y sus campos te los da `hbwidget read <widget>`")

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
    # V2-350 — el token viaja TAMBIÉN por esta puerta. Ya estaba en el entorno (lo usa `mem_cli`) y esta era la
    # única de las dos que no lo miraba: un worker HUÉRFANO —vivo, con el registro de su task_id ya sustituido
    # por el de su relevo— se comía un 403 al publicar y en cambio escribía sus notas en el estado del NUEVO.
    payload = {"tid": tid, "token": os.getenv("ZAELAR_TASK_TOKEN", ""), **payload}
    try:
        req = urllib.request.Request(
            _BASE + "/api/agent/report", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "zaelar-hbnote/1.0"}, method="POST")
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:  # noqa: BLE001
        print(f"report error: {e}", file=sys.stderr)
        return 1
    return 0


def _count(raw: str) -> int:
    """A step count as a worker writes it: «3», «3/5», «1,2,3» (the steps it lists), «paso 2». Measured 2026-10-14
    (search-buy-boat-multicountry ES): our own status demand said «--done <pasos hechos>» and the worker's call
    died on exit code 2, so the report it was told to give never arrived."""
    import argparse
    import re
    nums = re.findall(r"\d+", str(raw or ""))
    if not nums:
        raise argparse.ArgumentTypeError(f"«{raw}» is not a step count — pass the number of steps done, e.g. 3")
    if "," in raw or len(nums) > 2 or (len(nums) == 2 and "/" not in raw):
        return len(nums)                     # a list of the steps done: how many
    return int(nums[0])                      # «3» or «3/5»: the first number


def parser():
    """The CLI. Every subcommand that carries a free text also takes `--done`/`--pct`: the status demand names
    `phase` and `progress` in one sentence, and a worker that glued the flag onto `phase` (2026-10-14) lost its
    report to a usage error."""
    import argparse
    ap = argparse.ArgumentParser(prog="agent_report", description="Worker progress report to the FlashBrain")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("phase", "set the session's readable phase (visible to the operator)"),
                           ("note", "leave a trace in observability"),
                           ("progress", "report progress: note + --done N (steps done) and/or --pct P (0-100)")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("text", nargs="?" if name == "progress" else None, default="")
        p.add_argument("--done", type=_count, default=None)
        p.add_argument("--pct", type=_count, default=None)
    pl = sub.add_parser("plan", help="declare the TASK LIST at the start (steps separated by | )")
    pl.add_argument("text")
    go = sub.add_parser("goal", help="declare HOW success of this errand is measured (JSON, or @file.json)")
    go.add_argument("text")
    co = sub.add_parser("considered", help="BREADTH: how many candidates you really evaluated (--kept N finalists)")
    co.add_argument("n", type=_count)
    co.add_argument("--kept", type=_count, default=None)
    return ap


def _progress_body(a) -> dict:
    body: dict = {}
    if getattr(a, "done", None) is not None:
        body["done"] = a.done
    if getattr(a, "pct", None) is not None:
        body["pct"] = a.pct
    return body


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if a.cmd in ("phase", "note"):
        rc = _post({a.cmd: a.text})
        counts = _progress_body(a)
        return (_post({"progress": a.text, **counts}) or rc) if counts else rc
    if a.cmd == "plan":
        return _post({"plan": a.text})
    if a.cmd == "progress":
        return _post({"progress": a.text or "", **_progress_body(a)})
    if a.cmd == "goal":
        raw = a.text
        if raw.startswith("@"):
            try:
                with open(raw[1:], encoding="utf-8") as f:
                    raw = f.read()
            except OSError as e:
                print(f"no puedo leer el objetivo de {raw[1:]}: {e} — escríbelo primero con tu tool Write, "
                      f"a una ruta RELATIVA de tu directorio de trabajo.")
                return 2
        try:
            goal = json.loads(raw)
        except Exception as e:  # noqa: BLE001
            print(f"el objetivo no es JSON válido: {e}\n{_GOAL_HELP}")
            return 2
        return _post({"done_when": goal})
    if a.cmd == "considered":
        body = {"considered": a.n}
        if a.kept is not None:
            body["kept"] = a.kept
        return _post(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
