"""nucleo/widget_cli.py — `hbwidget`: el Brain Worker LEE y OPERA los widgets del canvas (V2-061).

Hermano de `hbweb` (nav_cli), `hbmem` (mem_cli), `hbnote` (agent_report) y `hbask/hbact/hbsay` (worker_bridge). Habla
por HTTP con el server vivo (`/api/worker/act`), id + token de la sesión por entorno (`ZAELAR_TASK_ID` +
`ZAELAR_TASK_TOKEN`, §v2·D). Fail-soft. Es el PUENTE que faltaba para las acciones ENCADENADAS realidad↔widgets:
tras ejecutar algo en el mundo real (cancelar una cita en una web) el worker REFLEJA el cambio en el ESPEJO local
(borra el appointment de la agenda), y verifica.

    python -m nucleo.widget_cli read agenda                      # LEE el widget: manifest + datos + ITEMS con su id
    python -m nucleo.widget_cli data agenda drop '{"itemId":"m_itv_23jul"}'   # DATA-OP (usa ids REALES de `read`)
    python -m nucleo.widget_cli data results present @informe.json           # PAYLOAD GRANDE: desde un fichero
    python -m nucleo.widget_cli show agenda                      # muestra la tarjeta en el canvas
    python -m nucleo.widget_cli close agenda                     # cierra la tarjeta

PAYLOAD DESDE FICHERO (`@ruta.json`, o `-` para stdin): úsalo SIEMPRE que el payload sea grande o lleve comillas,
acentos, URLs o saltos de línea — o sea, cualquier informe de verdad. Escribe el JSON a un fichero y pásalo con
`@`. Pegar 4 KB de JSON en la línea de comandos no funciona: se rompe con el quoting del shell y, si lo envuelves
en `"$(cat …)"`, el comando deja de ser reconocible y se queda esperando una aprobación que nadie va a dar (caso
real 2026-08-02: un worker terminó una búsqueda impecable de 9 minutos y el operador no llegó a ver ni un
resultado por esto).

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


#: Lo que teclea cualquiera —persona o modelo— al encontrarse una herramienta nueva. `nav_cli` lo contesta con
#: `exit 0` porque usa argparse; este puente lo contestaba con «comando desconocido» y `exit 2` (V2-325).
_AYUDA = ("--help", "-h", "help", "ayuda", "--ayuda", "-?", "/?")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd = argv[1]
    # PEDIR AYUDA NO ES UN FALLO (V2-325). Medido en los logs de sesión del plató (2026-08-25): de 332 sesiones
    # de worker, 81 usan `nav_cli` y solo 5 llegan a `widget_cli` — y TRES de esas cinco mueren en `Exit code 2`.
    # El paso que las mata es el PRIMERO: el worker escribe `widget_cli --help`, que es lo que hace cualquiera
    # con una herramienta nueva, y recibía «comando desconocido: --help» con código 2. Dos errores seguidos y
    # abandona; el resultado es una hoja que solo se llena con lo que el extractor automático saca de un
    # listado, mientras todo lo que el worker aprende ABRIENDO fichas muere en su contexto.
    #
    # Su hermano `nav_cli` contesta `--help` con exit 0 porque usa argparse, y es el puente que sí se usa. Aquí
    # se arregla sin migrar a argparse —eso cambiaría el contrato de los verbos que ya funcionan— sino
    # reconociendo la pregunta y devolviendo ÉXITO: preguntar cómo se usa algo no es equivocarse.
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
                    # measured on `cheapest-monitor` (round 21), `Exit code 2 no puedo leer el payload de
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
                        try:
                            found = sorted(f for f in os.listdir(here) if f.endswith(".json"))
                        except OSError:
                            found = []
                        print(f"   · ruta RELATIVA a tu directorio de trabajo: {here}")
                        print("   · ficheros .json ahí: " + (", ".join(found) if found else "NINGUNO"))
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
    # …y un verbo que no existe DICE cuáles existen, en vez de dejar al que pregunta adivinando. Es la misma
    # cortesía que `nav_cli._hint_for`: el error que no enseña el camino cuesta otra vuelta entera.
    print(f"comando desconocido: {cmd}\n"
          f"verbos: read <widget> · data <widget> <accion> [payload|@fichero|-] · show <widget> · close <widget>\n"
          f"ayuda:  python -m nucleo.widget_cli --help")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
