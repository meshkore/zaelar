"""nucleo/widget_cli.py — `hbwidget`: the Brain Worker READS and OPERATES the canvas widgets (V2-061).

Sibling of `hbweb` (nav_cli), `hbmem` (mem_cli), `hbnote` (agent_report), and `hbask/hbact/hbsay` (worker_bridge). It
talks over HTTP to the live server (`/api/worker/act`), using the session id + token from the environment
(`ZAELAR_TASK_ID` + `ZAELAR_TASK_TOKEN`, §v2·D). Fail-soft. It is the missing BRIDGE for CHAINED reality↔widget
actions: after doing something in the real world (cancelling an appointment on a website), the worker REFLECTS the
change in the local MIRROR (deletes the appointment from the calendar), and verifies it.

    python -m nucleo.widget_cli read agenda                      # READ the widget: manifest + data + ITEMS with their ids
    python -m nucleo.widget_cli data agenda drop '{"itemId":"m_itv_23jul"}'   # DATA-OP (uses REAL ids from `read`)
    python -m nucleo.widget_cli data results present @informe.json           # LARGE PAYLOAD: from a file
    python -m nucleo.widget_cli show agenda                      # shows the card on the canvas
    python -m nucleo.widget_cli close agenda                     # closes the card

PAYLOAD FROM FILE (`@path.json`, or `-` for stdin): ALWAYS use it when the payload is large or contains quotes,
accents, URLs, or line breaks—in other words, any real report. Write the JSON to a file and pass it with `@`. Pasting
4 KB of JSON into the command line does not work: shell quoting breaks, and if you wrap it in `"$(cat …)"`, the
command is no longer recognizable and waits for an approval that nobody will give (real case 2026-08-02: a worker
completed a flawless 9-minute search and the operator did not see a single result because of this).

GOLDEN RULE: to operate an item, READ first (`read`) and use the REAL id it returns—NEVER invent ids or pass natural
language here (that belongs to FlashBrain). The gate is the catalog's: a FAST action is applied immediately; an
IRREVERSIBLE (CONFIRM) action asks the operator for approval and returns a corr_id (wait for it with `python -m
nucleo.worker_bridge wait <corr_id>`); an UNDECLARED action is DENIED (read it in the `read` manifest). Any response
may carry ⟦NEW INSTRUCTIONS⟧ (piggyback, §v3·H).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")


def _tid_token() -> tuple[str, str]:
    return os.getenv("ZAELAR_TASK_ID", "").strip(), os.getenv("ZAELAR_TASK_TOKEN", "").strip()


def _act(action: str, payload: dict) -> dict:
    tid, tok = _tid_token()
    if not tid:
        return {"ok": False, "error": "ZAELAR_TASK_ID no definido (no soy un worker gestionado)"}
    body = {"task_id": tid, "token": tok, "action": action, "payload": payload}
    try:
        req = urllib.request.Request(
            _BASE + "/api/worker/act", data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "zaelar-hbwidget/1.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _emit_injections(res: dict) -> None:
    for msg in (res or {}).get("injections") or []:
        print(f"⟦NUEVAS INSTRUCCIONES DEL OPERADOR⟧ {msg}")


def _report(res: dict) -> int:
    _emit_injections(res)
    if res.get("denied"):
        print("DENEGADO: " + str(res.get("error") or "acción no permitida (¿no está declarada en el manifest?)"))
        return 1
    if not res.get("ok"):
        print("ERROR: " + str(res.get("error") or "desconocido"))
        return 1
    if res.get("status") == "pending":
        print("PENDIENTE DE CONFIRMACIÓN del operador (acción irreversible). "
              f"Espera la respuesta con: python -m nucleo.worker_bridge wait {res.get('corr_id', '')}")
        return 0
    if res.get("result") is not None:
        print("OK: " + json.dumps(res["result"], ensure_ascii=False))
    else:
        print("OK")
    return 0


#: What anyone—person or model—types when encountering a new tool. `nav_cli` answers it with
#: `exit 0` because it uses argparse; this bridge used to answer with “unknown command” and `exit 2` (V2-325).
_AYUDA = ("--help", "-h", "help", "ayuda", "--ayuda", "-?", "/?")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    # ASKING FOR HELP IS NOT A FAILURE (V2-325). Measured in the studio session logs (2026-08-25): of 332 worker
    # sessions, 81 use `nav_cli` and only 5 reach `widget_cli`—and THREE of those five die with `Exit code 2`.
    # The first step is what kills them: the worker types `widget_cli --help`, as anyone does with a new tool,
    # and received “unknown command: --help” with code 2. After two consecutive errors it gives up; the result is
    # a sheet filled only with what the automatic extractor pulls from a listing, while everything the worker
    # learns by OPENING records dies in its context.
    #
    # Its sibling `nav_cli` answers `--help` with exit 0 because it uses argparse, and it is the bridge that gets used.
    # This is fixed without migrating to argparse—that would change the contract of verbs that already work—but by
    # recognizing the question and returning SUCCESS: asking how to use something is not making a mistake.
    if cmd in _AYUDA:
        print(__doc__)
        return 0
    if cmd == "read":
        if len(argv) < 3:
            print("uso: hbwidget read <widget_id>")
            return 2
        return _report(_act("read_widget", {"id": argv[2]}))
    if cmd in ("show", "close"):
        if len(argv) < 3:
            print(f"uso: hbwidget {cmd} <widget_id>")
            return 2
        return _report(_act(f"{cmd}_widget", {"id": argv[2]}))
    if cmd == "data":
        if len(argv) < 4:
            print("uso: hbwidget data <widget_id> <action> [payload-json]")
            return 2
        wid, action = argv[2], argv[3]
        payload = {}
        raw = argv[4].strip() if len(argv) >= 5 else ""
        if raw:
            src = "argumento"
            if raw == "-":
                raw, src = sys.stdin.read(), "stdin"
            elif raw.startswith("@"):
                path, src = raw[1:], f"fichero {raw[1:]}"
                try:
                    with open(path, encoding="utf-8") as f:
                        raw = f.read()
                except OSError as e:
                    # V2-203 — this message used to be the bare OSError, and the worker read it as a dead end:
                    # measured on `cheapest-monitor` (round 21), `Exit code 2 cannot read the payload from
                    # informe.json: [Errno 2] No such file or directory` ended the task with nothing delivered.
                    # It says WHAT failed and nothing about what to do, which is the fault `nav_cli` already paid
                    # for (V2-186): the bridge is the worker's only view, so a message without a way out is a
                    # message that stops it. The two facts it needs are WHERE it is looking (the path is relative,
                    # and a worker that wrote to another directory cannot tell from the error) and WHAT is
                    # actually there — writing `resultados.json` and presenting `informe.json` is invisible
                    # otherwise.
                    print(f"no puedo leer el payload de {path}: {e}")
                    if not os.path.isabs(path):
                        here = os.getcwd()
                        print(f"   · ruta RELATIVA a tu directorio de trabajo: {here}")
                        # MECHANISM SHARED with `worker_bridge` (same reason as `read_payload`): two bridges that
                        # answer the same question differently diverge again, and that divergence is exactly what
                        # led to V2-379.
                        from nucleo import bridge_usage as _bu
                        _hay = _bu.what_is_here()
                        if _hay:
                            print(f"   · {_hay}")
                        print("   · son DOS pasos y este es el segundo: escribe primero el JSON con tu tool Write "
                              f"a `{path}` (ruta relativa, sin /tmp/ ni rutas absolutas) y vuelve a lanzar esto.")
                    return 2
            try:
                payload = json.loads(raw)
            except Exception as e:  # noqa: BLE001
                print(f"el payload ({src}) no es JSON válido: {e}")
                return 2
            if not isinstance(payload, dict):
                print("el payload debe ser un objeto JSON")
                return 2
        return _report(_act("widget_data", {"widget_id": wid, "action": action, "payload": payload}))
    # …and a verb that does not exist SAYS which ones do, instead of leaving the asker to guess. It is the same
    # courtesy as `nav_cli._hint_for`: an error that does not show the way costs another full round.
    print(f"comando desconocido: {cmd}\n"
          f"verbos: read <widget> · data <widget> <accion> [payload|@fichero|-] · show <widget> · close <widget>\n"
          f"ayuda:  python -m nucleo.widget_cli --help")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
