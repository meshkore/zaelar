"""nucleo/widget_cli.py — `hbwidget`: el Brain Worker LEE y OPERA los widgets del canvas (V2-061).

Hermano de `hbweb` (nav_cli), `hbmem` (mem_cli), `hbnote` (agent_report) y `hbask/hbact/hbsay` (worker_bridge). Habla
por HTTP con el server vivo (`/api/worker/act`), id + token de la sesión por entorno (`ZAELAR_TASK_ID` +
`ZAELAR_TASK_TOKEN`, §v2·D). Fail-soft. Es el PUENTE que faltaba para las acciones ENCADENADAS realidad↔widgets:
tras ejecutar algo en el mundo real (cancelar una cita en una web) el worker REFLEJA el cambio en el ESPEJO local
(borra el appointment de la agenda), y verifica.

    python -m nucleo.widget_cli read agenda                      # LEE el widget: manifest + datos + ITEMS con su id
    python -m nucleo.widget_cli data agenda drop '{"itemId":"m_itv_23jul"}'   # DATA-OP (usa ids REALES de `read`)
    python -m nucleo.widget_cli show agenda                      # muestra la tarjeta en el canvas
    python -m nucleo.widget_cli close agenda                     # cierra la tarjeta

REGLA DE ORO: para operar un item, LEE primero (`read`) y usa el id REAL que te devuelve — NUNCA inventes ids ni
pases lenguaje natural aquí (eso es del FlashBrain). El gate es el del catálogo: una acción FAST se aplica ya; una
IRREVERSIBLE (CONFIRM) pide OK al operador y te devuelve un corr_id (espéralo con `python -m nucleo.worker_bridge
wait <corr_id>`); una acción NO declarada se DENIEGA (léela en el manifest de `read`). Toda respuesta puede arrastrar
⟦NUEVAS INSTRUCCIONES⟧ (piggyback, §v3·H).
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


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
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
        if len(argv) >= 5 and argv[4].strip():
            try:
                payload = json.loads(argv[4])
            except Exception as e:  # noqa: BLE001
                print(f"payload no es JSON válido: {e}")
                return 2
        return _report(_act("widget_data", {"widget_id": wid, "action": action, "payload": payload}))
    print(f"comando desconocido: {cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
