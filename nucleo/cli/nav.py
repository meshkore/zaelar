"""nucleo/cli/nav.py — `hbweb`: CLI with which a Claude Code worker DRIVES zaelar's browser (V2-036 F3).

The agent directs zaelar's Chromium step by step with ITS intelligence (not a cheap loop). The tab/task id comes from
`ZAELAR_TASK_ID` (injected by the dispatcher). Each action returns the page STATE (URL, title, and interactive
elements with their refs) so the agent can reason about the next step:

    python -m nucleo.cli.nav look                          # VISION: PNG path (Read) + coordinates → click_at/type_at
    python -m nucleo.cli.nav snapshot                      # interactive elements with [ref]
    python -m nucleo.cli.nav navigate "https://es.wallapop.com/search?keywords=moto+enduro"
    python -m nucleo.cli.nav click 12                      # click the [12] element from the LAST snapshot
    python -m nucleo.cli.nav type 7 "moto enduro 250" --submit
    python -m nucleo.cli.nav click_at 640 300              # VISION: click at capture pixels
    python -m nucleo.cli.nav type_at 300 220 "7465JKY" --submit   # VISION: click at (x,y) and type
    python -m nucleo.cli.nav scroll 800
    python -m nucleo.cli.nav extract                       # listings/results from the current page (JSON)

VISION flow (robust for forms): `look` → Read the PNG → `click_at`/`type_at` by coordinates → `look` again.
DOM flow: `snapshot` → choose a ref → `click`/`type` → new snapshot → repeat → `extract` at the end.
It communicates over HTTP with the live server (ZAELAR_BASE, default localhost:43917). Fail-soft.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

from nucleo.cli import usage as bridge_usage

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")


#: How long we wait for one browser ANSWER (not the action). The error message names this number, so it lives once.
#: A working action takes seconds (measured: navigate/look 4.2 s, extract 0.05 s); 25 s is six times that and too
#: short to conceal a hang — no ninety-second timeouts.
_ACT_TIMEOUT_S = 25


def _act(action: str, args: dict) -> dict:
    # The browser is keyed by the NAVTASK id (the tab/card), not by the dispatcher's escalation id.
    tid = (os.getenv("ZAELAR_NAV_TASK") or os.getenv("ZAELAR_TASK_ID") or "").strip()
    if not tid:
        return {"ok": False, "error": "ZAELAR_NAV_TASK no definido (no soy un worker de navegador gestionado)"}
    payload = {"task_id": tid, "action": action, "args": args}
    try:
        req = urllib.request.Request(
            _BASE + "/api/navegador/act", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "zaelar-hbweb/1.0"}, method="POST")
        with urllib.request.urlopen(req, timeout=_ACT_TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8") or "{}")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": _transport_error(e, action)}


def _transport_error(e: Exception, action: str) -> str:
    """What went wrong AND how to get out of it — because this CLI is the worker's whole view of this side.

    A bare «timed out» says nothing about what to do (node 4.20: a failure also says how to get out of it).
      · TIMEOUT — we gave up on the ANSWER; the action may still be RUNNING. Repeating it queues a second action
        on a busy browser, so the way out is to LOOK at where the page ended up.
      · UNREACHABLE — the engine is not answering; nothing will move, so stop retrying and deliver.
    Anything else keeps its own text: no invented diagnosis (V2-248 — reject rather than guess).
    """
    txt = str(e) or e.__class__.__name__
    low = txt.lower()
    if isinstance(e, TimeoutError) or "timed out" in low or "timeout" in low:
        return (f"el navegador no ha contestado a «{action}» en {_ACT_TIMEOUT_S}s. OJO: eso NO quiere decir "
                f"que no se haya hecho — la acción puede seguir corriendo en la pestaña. NO la repitas (se "
                f"encolaría encima de una pestaña ocupada): espera un poco y haz `look` para ver dónde ha "
                f"acabado la página de verdad, y sigue desde ahí.")
    if isinstance(e, (ConnectionError, OSError)) and (
            "refused" in low or "connection" in low or "not known" in low or "unreachable" in low):
        return (f"no puedo hablar con el motor ({txt}), así que el navegador no se va a mover con ningún "
                f"comando. No insistas con esto: entrega lo que ya tengas y dilo.")
    return txt


# V2-212 — `type` takes a [ref], `type_at` takes COORDINATES; a worker mixing them gets only argparse's `usage`
# (the FORM, not the error), so `_hint_for` adds what to do.
_SCROLL_STEP = 800
# V2-219 — `scroll down` is what a worker writes. Accepting the word classifies no intent: the direction already
# IS the argument; this only stops the CLI rejecting its most natural spelling.
_SCROLL_WORDS = {"down": _SCROLL_STEP, "abajo": _SCROLL_STEP, "up": -_SCROLL_STEP, "arriba": -_SCROLL_STEP,
                 "bottom": _SCROLL_STEP * 5, "top": -_SCROLL_STEP * 5}


def _scroll_amount(raw: str) -> int:
    """Pixels. A bare direction resolves to one screenful; a number still means exactly that number."""
    v = (raw or "").strip().lower()
    if v in _SCROLL_WORDS:
        return _SCROLL_WORDS[v]
    try:
        return int(v)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"«{raw}» no es ni un número de píxeles ni una dirección. Usa `scroll 800`, o `scroll down` / "
            f"`scroll up` si solo quieres moverte una pantalla.")


def _hint_for(prog: str) -> str:
    if prog.endswith("type_at"):
        return ("   · `type_at` es de VISIÓN y va con COORDENADAS: `type_at <x> <y> \"texto\"`, dos números "
                "sacados de la captura (`look`).\n"
                "   · Si lo que tienes es un [ref] del snapshot, el comando es OTRO: `type <ref> \"texto\"`.\n"
                "   · El texto va ENTRE COMILLAS si lleva espacios; si no, se parte y el segundo trozo cae donde "
                "va una coordenada.")
    if prog.endswith("scroll"):
        return ("   · `scroll` va en PÍXELES: `scroll 800` baja una pantalla, `scroll -800` sube.\n"
                "   · También acepta la dirección sola: `scroll down` / `scroll up`.")
    if prog.endswith("click_at"):
        return ("   · `click_at` es de VISIÓN y va con COORDENADAS: `click_at <x> <y>` (de la captura de `look`).\n"
                "   · Con un [ref] del snapshot el comando es `click <ref>`.")
    # V2-369 — verbs that take a URL. Measured in `rental-car-automatic-airport__es` (2026-08-27): the
    # worker wrote `cli.nav navigate` with NO ARGUMENT at 32 s, received only the `usage:`, and **wrote it again
    # without an argument 42 s later**; `visit` did the same. In the SAME session, bare `cli.bridge act` —which
    # does provide a hint—failed ONCE and was not repeated. That is the measure: the one with a hint self-corrects;
    # the one that only receives the form repeats it. The first three minutes were lost there and the task reached
    # no rental site; the sheet ended up with search-results-page titles.
    if prog.endswith(("navigate", "open", "goto", "visit")):
        _verbo = prog.rsplit(" ", 1)[-1] or "navigate"
        return (f"   · A `{_verbo}` le falta LA DIRECCIÓN, y va pegada detrás en el MISMO comando: "
                f"`{_verbo} https://www.ejemplo.es/...`.\n"
                "   · La dirección va ENTERA, con `https://` — un dominio a secas no es una dirección.\n"
                "   · Si no sabes a dónde ir todavía, no adivines la dirección: busca primero.\n"
                "   · NO lo repitas igual: sin dirección va a fallar las veces que haga falta.")
    return ""


# A `usage` message states the FORM; this adds WHAT to do. This is node 4.20's contract applied to arguments: what
# the bridge knows, it says — and a failure also says how to get out of it. The mechanism is shared (V2-219); what
# belongs to this bridge is `_hint_for`.
_GuidedParser = bridge_usage.guided(_hint_for)


def _ref(v: str) -> int:
    """A `ref` with the brackets that WE render is a ref, not a syntax error (V2-341).

    `dom.py` renderiza cada elemento como `[2] button "Buscar"` y el propio encabezado de `_print_state` dice
    «usa el numero [ref] con click/type» — o sea que la forma con corchetes es la que el worker tiene DELANTE
    cuando escribe el comando. Medido en los logs de sesion del plato: `cli.nav type: error: argument ref:
    invalid int value: '[2]'`. Same rule as V2-306/V2-219: copying literally what we show it must not cost a turn.
    """
    return int(str(v).strip().strip("[]"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cli.nav", description="Conduce el navegador de zaelar (worker Claude Code)")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_GuidedParser)
    sub.add_parser("snapshot", help="estado + elementos interactivos de la página actual")
    sub.add_parser("look", help="VISIÓN: captura la página → ruta PNG para Read + coordenadas para click_at/type_at")
    # V2-306 — `open`/`goto` are ALIASES of navigate, and it is the CLI that was wrong, not the worker (the
    # V2-219 rule). Measured on `find-best-hotel-city__es` (2026-08-25 02:22): TWO workers in a row wrote
    # `cli.nav open <url>` — the natural verb, and the one our own recipe teaches in prose («para ABRIR una
    # page uses…») — and burned their turns on «invalid choice: 'open'» while the round ended with an empty
    # sheet. An alias keeps the semantics identical; a hint on the error would still cost the failed call.
    n = sub.add_parser("navigate", aliases=["open", "goto"], help="ir a una URL"); n.add_argument("url")
    c = sub.add_parser("click", help="click en un [ref] del último snapshot"); c.add_argument("ref", type=_ref)
    t = sub.add_parser("type", help="escribir en un [ref]"); t.add_argument("ref", type=_ref)
    t.add_argument("text"); t.add_argument("--submit", action="store_true")
    so = sub.add_parser("select_option", help="elegir opción de un <select> [ref] por texto/valor o --index")
    so.add_argument("ref", type=_ref); so.add_argument("value", nargs="?", default="")
    so.add_argument("--index", type=int, default=None)
    ca = sub.add_parser("click_at", help="VISIÓN: click en coordenadas (x y) de la captura")
    ca.add_argument("x", type=int); ca.add_argument("y", type=int)
    ta = sub.add_parser("type_at", help="VISIÓN: click en (x y) y escribir texto")
    ta.add_argument("x", type=int); ta.add_argument("y", type=int)
    ta.add_argument("text"); ta.add_argument("--submit", action="store_true")
    s = sub.add_parser("scroll", help="desplazar (píxeles, o `down`/`up`)")
    s.add_argument("dy", type=_scroll_amount, nargs="?", default=_SCROLL_STEP)
    p = sub.add_parser("press", help="pulsar una tecla"); p.add_argument("key", nargs="?", default="Enter")
    e = sub.add_parser("extract", help="raspar anuncios/resultados"); e.add_argument("--limit", type=int, default=14)
    v = sub.add_parser("visit", help="abrir UNA ficha en otra pestaña, leerla y cerrarla (NO pierdes el listado)")
    v.add_argument("url"); v.add_argument("--chars", type=int, default=2500)
    # V2-341 — two unambiguous forms the worker writes: `cli.nav <url>` (a bare URL can only be `navigate`) and
    # `type_at <ref> "text"` (two args, the second not a number, can only be `type`). Not guesses about intent.
    # WATCH THE INDEX: the VERB is at position 0 of `sys.argv[1:]`, not 1 (tests pass a list and hid that crash).
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        if argv[0].startswith(("http://", "https://")):
            argv.insert(0, "navigate")
        elif argv[0] == "type_at" and len(argv) == 3:
            try:
                int(argv[2])          # partial `type_at x y`: do NOT touch this; let argparse report it
            except ValueError:
                argv[0] = "type"      # `type_at <ref> "text"` -> the usual `type`
    a = ap.parse_args(argv)
    if a.cmd in ("open", "goto"):     # V2-306: argparse keeps the alias the caller typed; the dispatch is one
        a.cmd = "navigate"
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
    elif a.cmd == "visit":
        res = _act("visit", {"url": a.url, "chars": a.chars})
    elif a.cmd == "scroll":
        res = _act("scroll", {"dy": a.dy})
    elif a.cmd == "press":
        res = _act("press", {"key": a.key})
    elif a.cmd == "extract":
        res = _act("extract", {"limit": a.limit})
    else:
        return 2
    _note_source(a.cmd, res)
    _print_state(res)
    return 0 if res.get("ok") else 1


def _note_source(cmd: str, res: dict) -> None:
    """V2-798 · what this page did goes to the per-source record the NEXT worker reads in its step 0.

    Two facts are observed here and nowhere else on the worker's side: the page is a WALL (403, CAPTCHA, login),
    and `extract` found no named row on it — or found some, which is the positive fact that makes a site worth
    starting with. Fail-soft: the worker's answer is printed whatever happens here."""
    try:
        from nucleo.workers import source_outcomes as so
        src = so.source_of_url(str((res or {}).get("url") or ""))
        if not src or not res.get("ok"):
            return
        if res.get("wall"):
            so.note(src, so.WALL, detail=str(res["wall"]))
        elif cmd == "extract":
            named = [x for x in (res.get("listings") or []) if isinstance(x, dict) and x.get("title")]
            so.note(src, so.SERVED if named else so.EXTRACT_EMPTY, detail=f"{len(named)} rows")
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"source_note_failed": str(e)[:200]}), file=sys.stderr)


from nucleo.cli.nav_print import (  # noqa: E402,F401 — moved by concern (refactor2710-10b)
    _QUE_HACER, _print_state, _salida, _sees)


if __name__ == "__main__":
    raise SystemExit(main())
