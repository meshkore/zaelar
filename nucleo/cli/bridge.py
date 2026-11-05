"""nucleo/cli/bridge.py — `hbask`/`hbact`/`hbsay`: bridges from the Brain Worker → FlashBrain/user (V2-038).

A Brain Worker (subprocess, any backend) invokes them through Bash to INTERACT while working — the
request/response layer of the design (§v2·B, §v3·I). Same pattern as `hbnote`/`hbmem`/`hbweb`: communicates over HTTP
with the live server, using the session id + token from the environment (`ZAELAR_TASK_ID` + `ZAELAR_TASK_TOKEN`, §v2·D). Fail-soft.

    python -m nucleo.cli.bridge ask "¿la prefieres de enduro o de cross?"
    python -m nucleo.cli.bridge wait <corr_id>            # one look: the answer, or end the turn (the task resumes)
    python -m nucleo.cli.bridge act use_tool '{"tool":"web_search","args":{"query":"precio moto enduro"}}'
    python -m nucleo.cli.bridge say "voy a tardar un poco más, sigo filtrando"
    python -m nucleo.cli.bridge catalog browser            # a family's full set (V2-851 F3: the brief has headlines)

Any response may carry ⟦NUEVAS INSTRUCCIONES⟧ (piggyback, §v3·H): if the operator refined the task
("also, green"), the worker learns about it here without depending on the engine's turn-taking.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

from nucleo.cli import usage as bridge_usage

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")


def _tid_token() -> tuple[str, str]:
    return os.getenv("ZAELAR_TASK_ID", "").strip(), os.getenv("ZAELAR_TASK_TOKEN", "").strip()


def _post(path: str, payload: dict) -> dict:
    try:
        req = urllib.request.Request(
            _BASE + path, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "zaelar-worker-bridge/1.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _get(path: str) -> dict:
    try:
        req = urllib.request.Request(_BASE + path, headers={"User-Agent": "zaelar-worker-bridge/1.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _emit_injections(res: dict) -> None:
    inj = (res or {}).get("injections") or []
    for msg in inj:
        print(f"⟦NUEVAS INSTRUCCIONES DEL OPERADOR⟧ {msg}")


#: What the worker is told once its question is recorded (V2-851 §3): its process ends here and the task resumes
#: THIS session, by id, with his answer. Waiting in a loop kept a process alive for a reply that may take days.
_END_TURN = ("QUESTION RECORDED (ask_id {ask_id}). The task now WAITS for the operator's answer on its row. END YOUR "
             "TURN NOW: do nothing else and do not wait or poll. This session is resumed with his answer.")


def _poll_until(corr_id: str) -> int:
    """ONE look at a recorded question: its answer if it already came, otherwise the order to end the turn."""
    res = _get(f"/api/worker/act/{corr_id}")
    _emit_injections(res)
    if res.get("status") == "answered":
        print(f"RESPUESTA DEL OPERADOR: {res.get('answer', '')}")
        if res.get("result") is not None:
            print("RESULTADO: " + json.dumps(res["result"], ensure_ascii=False))
        return 0
    print(_END_TURN.format(ask_id=corr_id))
    return 0


def _cmd_ask(question: str, options: list[str] | None = None) -> int:
    tid, tok = _tid_token()
    if not tid:
        print("ZAELAR_TASK_ID no definido (no soy un worker gestionado)", file=sys.stderr)
        return 1
    payload = {"question": question, **({"options": list(options)} if options else {})}
    res = _post("/api/worker/act", {"task_id": tid, "token": tok, "action": "ask_user", "payload": payload})
    _emit_injections(res)
    if not res.get("ok"):
        print(f"(no pude preguntar: {res.get('error')})", file=sys.stderr)
        return 1
    corr = res.get("corr_id", "")
    if not corr:
        return 1
    print(_END_TURN.format(ask_id=corr))
    return 0


def _cmd_act(action: str, payload_json: str) -> int:
    tid, tok = _tid_token()
    if not tid:
        print("ZAELAR_TASK_ID no definido", file=sys.stderr)
        return 1
    # V2-379 — the payload may be inline, via `@file`, or via `-`. Inline does NOT ALWAYS FIT: our own
    # permission gate rejects an argument containing braces and quotes, and without an alternative the worker
    # cannot request a search. See `bridge_usage.read_payload` for the measured trace.
    from nucleo.cli import usage as _bu
    _raw, _src, _err = _bu.read_payload(payload_json)
    if _err:
        print(f"no puedo leer el payload de {payload_json[1:]}: {_err}", file=sys.stderr)
        print(f"   · ruta RELATIVA a tu directorio de trabajo: {os.getcwd()}", file=sys.stderr)
        # WHAT IS THERE, not just what is missing: «does not exist» alone does not distinguish between writing it
        # somewhere else, writing it under another name, and not writing it — three different outcomes that look
        # identical from there. See `bridge_usage.what_is_here`.
        _hay = _bu.what_is_here()
        if _hay:
            print(f"   · {_hay}", file=sys.stderr)
        print("   · son DOS pasos y este es el segundo: escribe primero el JSON con tu tool Write a esa ruta "
              "(relativa, sin /tmp/ ni rutas absolutas) y vuelve a lanzar esto.", file=sys.stderr)
        return 1
    # WHAT was invalid about it, not merely that it was invalid — while tolerating the Markdown fence. See
    # `parse_payload`: this is anomaly no. 1 on the entire board, and its message provided nothing to fix it.
    payload, _perr = _bu.parse_payload(_raw)
    if _perr:
        # V2-469 — a plain-text payload for web_search IS the query (V2-341's rule: the natural shape must
        # not cost the turn). Anything else keeps the honest error. See `bridge_usage.bare_query_payload`.
        _bare = _bu.bare_query_payload(action, _raw)
        if _bare is not None:
            payload = _bare
        else:
            print(f"payload JSON inválido ({_src}): {_perr}", file=sys.stderr)
            return 1
    res = _post("/api/worker/act", {"task_id": tid, "token": tok, "action": action, "payload": payload})
    _emit_injections(res)
    if res.get("denied"):
        print(f"ACCIÓN DENEGADA: {res.get('error')}")
        return 0
    if res.get("status") == "pending" and res.get("corr_id"):
        print(_END_TURN.format(ask_id=res["corr_id"]))   # a CONFIRM is a question: the task waits on its row
        return 0
    if res.get("ok"):
        if res.get("result") is not None:
            print("RESULTADO: " + json.dumps(res["result"], ensure_ascii=False))
        else:
            print("OK")
        return 0
    print(f"(acción falló: {res.get('error')})", file=sys.stderr)
    return 1


def _cmd_catalog(family: str) -> int:
    """A family's full set of the two-layer catalogue (V2-851 F3) — read locally, nothing leaves the machine."""
    from nucleo.workers.prompts import catalog
    print(catalog.full(family))
    return 0


def _cmd_say(text: str) -> int:
    tid, tok = _tid_token()
    if not tid:
        print("ZAELAR_TASK_ID no definido", file=sys.stderr)
        return 1
    res = _post("/api/worker/say", {"task_id": tid, "token": tok, "text": text})
    _emit_injections(res)
    return 0 if res.get("ok") else 1


# V2-219 — measured in `hotel-under-15-days`: `Exit code 2 usage: cli.bridge [-h] {ask,wait,act,say} … error:
# the following arguments are required`. The worker got stuck there and the round ended with ZERO searches. A `usage`
# message shows the form but not what to do, which is the dead end already paid for by `cli.nav` (V2-212) and the
# payload bridge (V2-203). It hurts more here than anywhere else: `cli.bridge` is how the worker REQUESTS a
# search, so dying on its arguments leaves it blind for the rest of the task.
def _hint_for(prog: str) -> str:
    if prog.endswith("act"):
        return ('   · `act` lleva DOS cosas: la acción y su payload JSON ENTRE COMILLAS SIMPLES.\n'
                '   · Para BUSCAR en la web (lo más habitual):\n'
                '       act use_tool "<qué buscas>"\n'
                '   · El JSON va en UNA sola línea y con comillas simples por fuera: sin ellas el shell lo parte '
                'y llega a medias.\n'
                # V2-379 — the fallback when inline JSON DOES NOT PASS. Our own gate rejects an argument
                # containing braces and quotes, and without saying this the worker keeps going in circles:
                # measured, it found the file workaround on its own and the bridge did not know how to read it.
                '   · Si te lo rechazan por las llaves («brace with quote»), escribe el JSON a un fichero con '
                'Write y pásalo con arroba: `act use_tool @busqueda.json` (ruta RELATIVA a tu directorio). '
                'También vale `-` para leerlo de la entrada estándar.')
    if prog.endswith("ask"):
        return ('   · `ask` lleva la pregunta ENTERA entre comillas: `ask "¿la prefieres de enduro o de cross?"`.\n'
                '   · Sin comillas se parte por los espacios y solo llega la primera palabra.\n'
                '   · Opciones declaradas (si las hay): `ask "¿cuál?" --option "Ana Pérez" --option "Ana Ruiz"`.\n'
                '   · No bloquea: la pregunta queda en la fila de la tarea, terminas tu turno y se te reanuda con su '
                'respuesta.')
    if prog.endswith("say"):
        return '   · `say` lleva el mensaje entre comillas: `say "voy a tardar un poco más, sigo filtrando"`.'
    if prog.endswith("wait"):
        return '   · `wait` lleva el `corr_id` que te devolvió el `ask` que lanzaste antes: `wait <corr_id>`.'
    if prog.endswith("decide"):
        return "   · " + _hint_decide()
    if prog.endswith("catalog"):
        from nucleo.workers.prompts import catalog
        return "   · `catalog <family>` — " + ", ".join(catalog.FAMILIES)
    return ("   · Los subcomandos son `ask` / `wait` / `act` / `say` / `decide` / `catalog`, y TODOS llevan su argumento entre "
            "comillas. Ninguno funciona a secas.")


def _hint_decide() -> str:
    """What `decide` is FOR, printed when a worker gets its shape wrong.

    Same two steps as every other payload on this bridge — write the JSON to a RELATIVE file with
    your Write tool, then pass `@that-file.json` — and for the same measured reason: our own
    permission gate rejects an argument containing braces and quotes, so an inline JSON never
    reaches the command at all (V2-379). A capability the worker cannot invoke is a capability it
    will narrate instead of using.
    """
    return ('python -m nucleo.cli.bridge decide @elige.json  ·  el fichero lleva\n'
            '   {"purpose": "cuál de estos pisos cumple los criterios",\n'
            '    "evidence": "menos de 1000 €, 2 habitaciones, Chamberí",\n'
            '    "candidates": {"r1": "piso en Malasaña, 1200 €", "r2": "piso en Chamberí, 900 €"}}\n'
            '   · `candidates` admite también una LISTA; los ids serán 1, 2, 3…\n'
            '   · responde {"status", "chosen", "confidence"}: `selected` trae la elección, '
            '`abstained` es «ninguno encaja»,\n'
            '     y `unavailable`/`disabled` significan que NADIE eligió — no que no haya candidato '
            'bueno.')


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="cli.bridge", description="Puentes del Brain Worker (ask/act/say/wait)")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=bridge_usage.guided(_hint_for))
    pa = sub.add_parser("ask", help="pregunta al usuario; la tarea espera su respuesta y se te reanuda con ella")
    pa.add_argument("question")
    pa.add_argument("--option", action="append", default=[], help="una opción declarada (repetible)")
    pw = sub.add_parser("wait", help="reintenta la espera de una pregunta ya hecha")
    pw.add_argument("corr_id")
    pc = sub.add_parser("act", help="pide una acción mediada (use_tool/read_widget/show_widget/widget_data/spawn)")
    pc.add_argument("action")
    pc.add_argument("payload", nargs="?", default="")
    ps = sub.add_parser("say", help="dile algo al usuario (se relata por voz con atribución)")
    ps.add_argument("text")
    pd = sub.add_parser("decide", help="elige entre candidatos que YA tienes (rápido y barato, sin razonador)")
    pd.add_argument("payload", help='@fichero.json con {"purpose", "candidates", "evidence"}')
    pk = sub.add_parser("catalog", help="the full set of one family of the catalogue (the brief carries headlines)")
    pk.add_argument("family")
    a = ap.parse_args(argv)
    if a.cmd == "ask":
        return _cmd_ask(a.question, a.option)
    if a.cmd == "wait":
        return _poll_until(a.corr_id)
    if a.cmd == "act":
        return _cmd_act(a.action, a.payload)
    if a.cmd == "say":
        return _cmd_say(a.text)
    if a.cmd == "decide":
        return _cmd_act("decide", a.payload)
    if a.cmd == "catalog":
        return _cmd_catalog(a.family)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
