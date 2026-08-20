"""nucleo/worker_bridge.py — `hbask`/`hbact`/`hbsay`: puentes del Brain Worker → FlashBrain/usuario (V2-038).

Un Brain Worker (subproceso, cualquier backend) los invoca por Bash para INTERACTUAR mientras trabaja — el plano
request/response del diseño (§v2·B, §v3·I). Igual patrón que `hbnote`/`hbmem`/`hbweb`: habla por HTTP con el server
vivo, id + token de la sesión por entorno (`ZAELAR_TASK_ID` + `ZAELAR_TASK_TOKEN`, §v2·D). Fail-soft.

    python -m nucleo.worker_bridge ask "¿la prefieres de enduro o de cross?"
    python -m nucleo.worker_bridge wait <corr_id>            # reintenta la espera (no agota el timeout del Bash)
    python -m nucleo.worker_bridge act use_tool '{"tool":"web_search","args":{"query":"precio moto enduro"}}'
    python -m nucleo.worker_bridge say "voy a tardar un poco más, sigo filtrando"

Toda respuesta puede arrastrar ⟦NUEVAS INSTRUCCIONES⟧ (piggyback, §v3·H): si el operador refinó la tarea
("además, verde"), el worker se entera aquí sin depender del turn-taking del motor.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

from nucleo import bridge_usage

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")
# Ventana de espera de UN ciclo de `ask`/`wait` — corta para retornar ANTES del timeout del tool Bash (§v3·I).
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
    """Un CICLO de espera acotado. Imprime la respuesta si llega; si no, dice cómo reintentar (§v3·I)."""
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
    try:
        payload = json.loads(payload_json) if payload_json else {}
    except Exception:
        print("payload JSON inválido", file=sys.stderr)
        return 1
    res = _post("/api/worker/act", {"task_id": tid, "token": tok, "action": action, "payload": payload})
    _emit_injections(res)
    if res.get("denied"):
        print(f"ACCIÓN DENEGADA: {res.get('error')}")
        return 0
    if res.get("status") == "pending" and res.get("corr_id"):
        return _poll_until(res["corr_id"])          # CONFIRM u otra que espera → esperamos como un ask
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


# V2-216 — medido en `hotel-under-15-days`: `Exit code 2 usage: worker_bridge [-h] {ask,wait,act,say} … error:
# the following arguments are required`. El worker se quedó ahí y la ronda acabó con CERO búsquedas. Un `usage`
# dice la forma y no dice qué hacer, que es el callejón sin salida que ya pagaron `nav_cli` (V2-212) y el puente
# del payload (V2-203). Aquí duele más que en ninguno: `worker_bridge` es la vía por la que el worker PIDE una
# búsqueda, así que morir en sus argumentos lo deja ciego para el resto de la tarea.
def _hint_for(prog: str) -> str:
    if prog.endswith("act"):
        return ('   · `act` lleva DOS cosas: la acción y su payload JSON ENTRE COMILLAS SIMPLES.\n'
                '   · Para BUSCAR en la web (lo más habitual):\n'
                '       act use_tool \'{"tool":"web_search","args":{"query":"<qué buscas>"}}\'\n'
                '   · El JSON va en UNA sola línea y con comillas simples por fuera: sin ellas el shell lo parte '
                'y llega a medias.')
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
