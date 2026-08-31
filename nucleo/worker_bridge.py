"""nucleo/worker_bridge.py — `hbask`/`hbact`/`hbsay`: bridges from the Brain Worker → FlashBrain/user (V2-038).

A Brain Worker (subprocess, any backend) invokes them through Bash to INTERACT while working — the
request/response layer of the design (§v2·B, §v3·I). Same pattern as `hbnote`/`hbmem`/`hbweb`: communicates over HTTP
with the live server, using the session id + token from the environment (`ZAELAR_TASK_ID` + `ZAELAR_TASK_TOKEN`, §v2·D). Fail-soft.

    python -m nucleo.worker_bridge ask "¿la prefieres de enduro o de cross?"
    python -m nucleo.worker_bridge wait <corr_id>            # retries the wait (does not exhaust the Bash timeout)
    python -m nucleo.worker_bridge act use_tool '{"tool":"web_search","args":{"query":"precio moto enduro"}}'
    python -m nucleo.worker_bridge say "voy a tardar un poco más, sigo filtrando"

Any response may carry ⟦NUEVAS INSTRUCCIONES⟧ (piggyback, §v3·H): if the operator refined the task
("also, green"), the worker learns about it here without depending on the engine's turn-taking.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

from nucleo import bridge_usage

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")
# Wait window for ONE `ask`/`wait` cycle — kept short to return BEFORE the Bash tool timeout (§v3·I).
_ASK_CYCLE_S = float(os.getenv("ZAELAR_ASK_CYCLE_S", "20"))
_POLL_EVERY_S = float(os.getenv("ZAELAR_ASK_POLL_S", "1.5"))


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


def _poll_until(corr_id: str) -> int:
    """One bounded wait CYCLE. Print the response if it arrives; otherwise explain how to retry (§v3·I)."""
    deadline = time.time() + _ASK_CYCLE_S
    while time.time() < deadline:
        res = _get(f"/api/worker/act/{corr_id}")
        _emit_injections(res)
        if res.get("status") == "answered":
            ans = res.get("answer", "")
            print(f"RESPUESTA DEL OPERADOR: {ans}")
            if res.get("result") is not None:
                print("RESULTADO: " + json.dumps(res["result"], ensure_ascii=False))
            return 0
        if not res.get("ok") and res.get("error"):
            print(f"(sin poder consultar: {res['error']})", file=sys.stderr)
            return 1
        time.sleep(_POLL_EVERY_S)
    print(f"sin respuesta aún — reintenta la espera con: python -m nucleo.worker_bridge wait {corr_id}")
    return 0


def _cmd_ask(question: str) -> int:
    tid, tok = _tid_token()
    if not tid:
        print("ZAELAR_TASK_ID no definido (no soy un worker gestionado)", file=sys.stderr)
        return 1
    res = _post("/api/worker/act", {"task_id": tid, "token": tok, "action": "ask_user",
                                    "payload": {"question": question}})
    _emit_injections(res)
    if not res.get("ok"):
        print(f"(no pude preguntar: {res.get('error')})", file=sys.stderr)
        return 1
    corr = res.get("corr_id", "")
    if not corr:
        return 1
    return _poll_until(corr)


def _cmd_act(action: str, payload_json: str) -> int:
    tid, tok = _tid_token()
    if not tid:
        print("ZAELAR_TASK_ID no definido", file=sys.stderr)
        return 1
    # V2-379 — the payload may be inline, via `@file`, or via `-`. Inline does NOT ALWAYS FIT: our own
    # permission gate rejects an argument containing braces and quotes, and without an alternative the worker
    # cannot request a search. See `bridge_usage.read_payload` for the measured trace.
    from nucleo import bridge_usage as _bu
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
        return _poll_until(res["corr_id"])          # CONFIRM or another action that waits → wait as for an ask
    if res.get("ok"):
        if res.get("result") is not None:
            print("RESULTADO: " + json.dumps(res["result"], ensure_ascii=False))
        else:
            print("OK")
        return 0
    print(f"(acción falló: {res.get('error')})", file=sys.stderr)
    return 1


def _cmd_say(text: str) -> int:
    tid, tok = _tid_token()
    if not tid:
        print("ZAELAR_TASK_ID no definido", file=sys.stderr)
        return 1
    res = _post("/api/worker/say", {"task_id": tid, "token": tok, "text": text})
    _emit_injections(res)
    return 0 if res.get("ok") else 1


# V2-219 — measured in `hotel-under-15-days`: `Exit code 2 usage: worker_bridge [-h] {ask,wait,act,say} … error:
# the following arguments are required`. The worker got stuck there and the round ended with ZERO searches. A `usage`
# message shows the form but not what to do, which is the dead end already paid for by `nav_cli` (V2-212) and the
# payload bridge (V2-203). It hurts more here than anywhere else: `worker_bridge` is how the worker REQUESTS a
# search, so dying on its arguments leaves it blind for the rest of the task.
def _hint_for(prog: str) -> str:
    if prog.endswith("act"):
        return ('   · `act` lleva DOS cosas: la acción y su payload JSON ENTRE COMILLAS SIMPLES.\n'
                '   · Para BUSCAR en la web (lo más habitual):\n'
                '       act use_tool \'{"tool":"web_search","args":{"query":"<qué buscas>"}}\'\n'
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
                '   · Bloquea hasta que el operador conteste; si vence el ciclo, reanúdala con `wait <corr_id>`.')
    if prog.endswith("say"):
        return '   · `say` lleva el mensaje entre comillas: `say "voy a tardar un poco más, sigo filtrando"`.'
    if prog.endswith("wait"):
        return '   · `wait` lleva el `corr_id` que te devolvió el `ask` que lanzaste antes: `wait <corr_id>`.'
    return ("   · Los subcomandos son `ask` / `wait` / `act` / `say`, y TODOS llevan su argumento entre "
            "comillas. Ninguno funciona a secas.")


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="worker_bridge", description="Puentes del Brain Worker (ask/act/say/wait)")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=bridge_usage.guided(_hint_for))
    pa = sub.add_parser("ask", help="pregunta al usuario y ESPERA la respuesta")
    pa.add_argument("question")
    pw = sub.add_parser("wait", help="reintenta la espera de una pregunta ya hecha")
    pw.add_argument("corr_id")
    pc = sub.add_parser("act", help="pide una acción mediada (use_tool/read_widget/show_widget/spawn/push_channel)")
    pc.add_argument("action")
    pc.add_argument("payload", nargs="?", default="")
    ps = sub.add_parser("say", help="dile algo al usuario (se relata por voz con atribución)")
    ps.add_argument("text")
    a = ap.parse_args(argv)
    if a.cmd == "ask":
        return _cmd_ask(a.question)
    if a.cmd == "wait":
        return _poll_until(a.corr_id)
    if a.cmd == "act":
        return _cmd_act(a.action, a.payload)
    if a.cmd == "say":
        return _cmd_say(a.text)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
