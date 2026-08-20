"""nucleo/nav_cli.py — `hbweb`: CLI con el que un worker Claude Code CONDUCE el navegador de zaelar (V2-036 F3).

El agente dirige el Chromium de zaelar paso a paso con SU inteligencia (no un bucle barato). El id de la pestaña/
tarea sale de `ZAELAR_TASK_ID` (lo inyecta el dispatcher). Cada acción devuelve el ESTADO de la página (url, título y
los elementos interactivos con su ref) para que el agente razone el siguiente paso:

    python -m nucleo.nav_cli look                          # VISIÓN: ruta PNG (Read) + coordenadas → click_at/type_at
    python -m nucleo.nav_cli snapshot                      # elementos interactivos con [ref]
    python -m nucleo.nav_cli navigate "https://es.wallapop.com/search?keywords=moto+enduro"
    python -m nucleo.nav_cli click 12                      # click en el elemento [12] del ÚLTIMO snapshot
    python -m nucleo.nav_cli type 7 "moto enduro 250" --submit
    python -m nucleo.nav_cli click_at 640 300              # VISIÓN: click en píxeles de la captura
    python -m nucleo.nav_cli type_at 300 220 "7465JKY" --submit   # VISIÓN: click en (x,y) y escribe
    python -m nucleo.nav_cli scroll 800
    python -m nucleo.nav_cli extract                       # anuncios/resultados de la página actual (JSON)

Flujo VISIÓN (robusto para formularios): `look` → Read el PNG → `click_at`/`type_at` por coordenadas → `look` otra
vez. Flujo DOM: `snapshot` → elige una ref → `click`/`type` → snapshot nuevo → repite → `extract` al final.
Habla por HTTP con el server vivo (ZAELAR_BASE, def localhost:43917). Fail-soft.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")


def _act(action: str, args: dict) -> dict:
    # el navegador se keyea por el id del NAVTASK (la pestaña/tarjeta), no por el id de la escalada del dispatcher.
    tid = (os.getenv("ZAELAR_NAV_TASK") or os.getenv("ZAELAR_TASK_ID") or "").strip()
    if not tid:
        return {"ok": False, "error": "ZAELAR_NAV_TASK no definido (no soy un worker de navegador gestionado)"}
    payload = {"task_id": tid, "action": action, "args": args}
    try:
        req = urllib.request.Request(
            _BASE + "/api/navegador/act", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "zaelar-hbweb/1.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _print_state(res: dict) -> None:
    if not res.get("ok"):
        print("ERROR: " + str(res.get("error") or res.get("msg") or "desconocido"))
        return
    if "listings" in res:
        print(json.dumps(res.get("listings", []), ensure_ascii=False, indent=2))
        return
    if res.get("msg"):
        print(res["msg"])
    # THE TWO FACTS THAT CHANGE WHAT TO DO NEXT GO FIRST — and until now they were thrown away here.
    # `/api/navegador/act` annotates every response with `wall` (V2-167: the page STOPPED us — anti-bot, CAPTCHA,
    # load error, «Access Denied» in the body) and with `hint`/`stalled_s` (V2-186: this page has not moved in
    # minutes). Both were added so the WORKER could act on them, because what comes back through this CLI is the
    # worker's entire view of the page — and this printer never printed either. Measured across four rounds of
    # `find-theatre-tickets__es` and `restaurant-tonight-madrid`: fourteen captures of one page over twenty
    # minutes, a whole run spent against Booking's challenge, and a task reported `done` while the operator was
    # told «aún no ha dado señal». Two fixes that travelled over HTTP and died one line short of their reader.
    # First, because a worker reads top-down and a wall means «stop trying here», not «keep scrolling».
    if res.get("wall"):
        print(f"⛔ MURO: {res['wall']} — esta página NO te va a dejar seguir. No insistas aquí: prueba otro "
              f"sitio, o si ya tienes algo aprovechable, extráelo y cierra.")
    if res.get("hint"):
        print(f"⚠️ AVISO: {res['hint']}")
    print(f"URL: {res.get('url', '')}")
    print(f"TÍTULO: {res.get('title', '')}")
    # V2-049 VISIÓN: si hay captura, dile al worker que la MIRE con Read (la página como la ve un humano) y actúe
    # por coordenadas con click_at/type_at — el camino robusto para formularios/date-pickers/selects.
    shot = res.get("shot")
    if shot:
        vp = res.get("viewport") or {"width": 1280, "height": 800}
        print(f"VISTA (captura {vp['width']}×{vp['height']} px — MÍRALA con Read \"{shot}\" y actúa con "
              f"click_at/type_at usando las coordenadas en píxeles): {shot}")
    els = res.get("elements") or ""
    print("ELEMENTOS INTERACTIVOS (usa el número [ref] con click/type):\n" + (els or "(ninguno)"))


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="nav_cli", description="Conduce el navegador de zaelar (worker Claude Code)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("snapshot", help="estado + elementos interactivos de la página actual")
    sub.add_parser("look", help="VISIÓN: captura la página → ruta PNG para Read + coordenadas para click_at/type_at")
    n = sub.add_parser("navigate", help="ir a una URL"); n.add_argument("url")
    c = sub.add_parser("click", help="click en un [ref] del último snapshot"); c.add_argument("ref", type=int)
    t = sub.add_parser("type", help="escribir en un [ref]"); t.add_argument("ref", type=int)
    t.add_argument("text"); t.add_argument("--submit", action="store_true")
    so = sub.add_parser("select_option", help="elegir opción de un <select> [ref] por texto/valor o --index")
    so.add_argument("ref", type=int); so.add_argument("value", nargs="?", default="")
    so.add_argument("--index", type=int, default=None)
    ca = sub.add_parser("click_at", help="VISIÓN: click en coordenadas (x y) de la captura")
    ca.add_argument("x", type=int); ca.add_argument("y", type=int)
    ta = sub.add_parser("type_at", help="VISIÓN: click en (x y) y escribir texto")
    ta.add_argument("x", type=int); ta.add_argument("y", type=int)
    ta.add_argument("text"); ta.add_argument("--submit", action="store_true")
    s = sub.add_parser("scroll", help="desplazar"); s.add_argument("dy", type=int, nargs="?", default=800)
    p = sub.add_parser("press", help="pulsar una tecla"); p.add_argument("key", nargs="?", default="Enter")
    e = sub.add_parser("extract", help="raspar anuncios/resultados"); e.add_argument("--limit", type=int, default=14)
    a = ap.parse_args(argv)
    if a.cmd == "snapshot":
        res = _act("snapshot", {})
    elif a.cmd == "look":
        res = _act("look", {})
    elif a.cmd == "navigate":
        res = _act("navigate", {"url": a.url})
    elif a.cmd == "click":
        res = _act("click", {"ref": a.ref})
    elif a.cmd == "type":
        res = _act("type", {"ref": a.ref, "text": a.text, "submit": bool(a.submit)})
    elif a.cmd == "select_option":
        args = {"ref": a.ref, "value": a.value}
        if a.index is not None:
            args["index"] = a.index
        res = _act("select_option", args)
    elif a.cmd == "click_at":
        res = _act("click_at", {"x": a.x, "y": a.y})
    elif a.cmd == "type_at":
        res = _act("type_at", {"x": a.x, "y": a.y, "text": a.text, "submit": bool(a.submit)})
    elif a.cmd == "scroll":
        res = _act("scroll", {"dy": a.dy})
    elif a.cmd == "press":
        res = _act("press", {"key": a.key})
    elif a.cmd == "extract":
        res = _act("extract", {"limit": a.limit})
    else:
        return 2
    _print_state(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
