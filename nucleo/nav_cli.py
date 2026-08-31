"""nucleo/nav_cli.py — `hbweb`: CLI with which a Claude Code worker DRIVES zaelar's browser (V2-036 F3).

The agent directs zaelar's Chromium step by step with ITS intelligence (not a cheap loop). The tab/task id comes from
`ZAELAR_TASK_ID` (injected by the dispatcher). Each action returns the page STATE (URL, title, and interactive
elements with their refs) so the agent can reason about the next step:

    python -m nucleo.nav_cli look                          # VISION: PNG path (Read) + coordinates → click_at/type_at
    python -m nucleo.nav_cli snapshot                      # interactive elements with [ref]
    python -m nucleo.nav_cli navigate "https://es.wallapop.com/search?keywords=moto+enduro"
    python -m nucleo.nav_cli click 12                      # click the [12] element from the LAST snapshot
    python -m nucleo.nav_cli type 7 "moto enduro 250" --submit
    python -m nucleo.nav_cli click_at 640 300              # VISION: click at capture pixels
    python -m nucleo.nav_cli type_at 300 220 "7465JKY" --submit   # VISION: click at (x,y) and type
    python -m nucleo.nav_cli scroll 800
    python -m nucleo.nav_cli extract                       # listings/results from the current page (JSON)

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

from nucleo import bridge_usage

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")


#: How long we wait for one browser action before giving up on the ANSWER (not on the action). The error
#: message NAMES this number, so it lives once: two literals drift and then the hint states a wrong figure.
# The browser is a DIRECT CONNECTION: an action that works completes in seconds. Measured against the
# live test rig on a real site: `navigate` 4.2 s · `look` 4.2 s · `extract` 0.05 s. It was 90 —twenty
# times the real cost— and that is not “ample margin”: a hang consumes a third of the round before anyone notices.
# Measured on 2026-08-24 in `search-buy-guitar__es`: 90 of 250 seconds in a `type` that HAD ALREADY WRITTEN the
# text. Operator rule that same day: “there are no ninety-second timeouts under any circumstances.” 25 s is still
# six times the real cost; it is not enough to conceal a hang.
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

    Measured on `search-secondhand-monitor__es` (2026-08-24 00:56): two `🧭 navegador ⚠️ error` reading
    «Exit code 1 ERROR: timed out», ninety seconds apart, and the round delivered zero results after having
    reached the right page. `str(socket.timeout())` is literally the two words «timed out» — true, and it
    says nothing about what to do. Same family as V2-203/V2-212/V2-248 and the same contract as node 4.20:
    what the bridge knows, it SAYS, and a failure also says how to get out of it.

    The distinction that changes what the worker does next, and it is the whole point of splitting these:

      · TIMEOUT — we gave up on the ANSWER; the action may well still be RUNNING in the browser. The
        natural reaction is to repeat it, and repeating is the one thing that cannot work: it queues a
        second action on a browser that is already busy. The way out is to LOOK at where the page actually
        ended up.
      · UNREACHABLE — the engine is not answering at all. Nothing in the browser will move, so retrying the
        same command forever is what a worker does when nobody tells it otherwise.

    Anything else keeps its own text: inventing a diagnosis for a failure we did not anticipate is how a
    hint stops being information (V2-248's lesson — reject rather than guess).
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


def _sees() -> bool:
    """Does the model driving this session read images? The serving stage declares this
    (`nucleo/workers/providers.vision_env`) and it arrives through the environment, which this CLI inherits from the worker.

    **Absent = yes**, the established behavior: an incorrect “cannot see” leaves a worker that could see blind,
    and that is a silent failure; an incorrect “can see” costs one failed `Read`, and the worker continues via the DOM."""
    return (os.environ.get("ZAELAR_NAV_VISION") or "").strip().lower() not in ("0", "false", "no")


#: Playwright failures encountered by the worker that do NOT say what to do. The raw message is preserved —it is
#: accurate and helps whoever debugs it— and the way out is appended, which is the only thing missing for the worker.
_QUE_HACER = (
    ("not attached to the dom",
     "El elemento ya no existe: la página se ha redibujado desde que miraste. Haz `look` otra vez y usa un "
     "ref del listado NUEVO — repetir el mismo número volverá a fallar."),
    ("element is not a <select>",
     "Eso no es un desplegable de verdad: muchos sitios los dibujan con divs. Haz `look` y haz `click` en el "
     "control y luego en la opción, como haría una persona."),
    ("timeout", "La página no ha contestado a tiempo. NO repitas la misma acción —se encolaría encima—: haz "
                "`look` para ver dónde ha quedado y decide desde ahí."),
)


def _salida(error: str) -> str:
    """What to do next if this error has a known way out. `` if it does not.

    Measured on 2026-08-28 on the 24/7 test rig: **seven** `click` calls against dead elements (“Element is not
    attached to the DOM”) across two rounds, and the message said nothing else. Its sibling —the ref outside the
    view— has always said so (“Run `look` … do not invent refs or retry the same one”), and that asymmetry has no
    justification: both are the same problem, an expired ref.
    """
    low = (error or "").lower()
    for aguja, salida in _QUE_HACER:
        if aguja in low:
            return salida
    return ""


def _print_state(res: dict) -> None:
    if not res.get("ok"):
        _err = str(res.get("error") or res.get("msg") or "desconocido")
        _sal = _salida(_err)
        print("ERROR: " + _err + (f" · {_sal}" if _sal else ""))
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
    # told “it still had not signaled.” Two fixes that travelled over HTTP and died one line short of their reader.
    # First, because a worker reads top-down and a wall means «stop trying here», not «keep scrolling».
    if res.get("wall"):
        print(f"⛔ MURO: {res['wall']} — esta página NO te va a dejar seguir. No insistas aquí: prueba otro "
              f"sitio, o si ya tienes algo aprovechable, extráelo y cierra.")
        # V2-213: and WHICH ONE. “Try another site” without naming one is a wish; the stuck worker is the one that does not know where to go. The alternatives are listed with the host that just blocked us excluded.
        for _a in (res.get("wall_alts") or [])[:3]:
            print(f"   → prueba en {_a.get('name', '')}: {_a.get('url', '')}")
        # V2-470 — when the walls span SEVERAL sites, the browser channel itself is being refused and another
        # retailer is a treadmill, not an alternative. Measured (`cheapest-monitor__us` round 11): 28
        # navigations across four walled retailers with `web_search` available the whole time, sheet 0 rows.
        _streak = res.get("wall_streak") or {}
        if _streak:
            _sites = ", ".join(_streak.get("sites") or [])
            print(f"⛔ RACHA DE MUROS: ya te han bloqueado {_streak.get('n')} veces en varios sitios ({_sites}). "
                  f"NO sigas navegando para conseguir estos datos: pídelos con la búsqueda web por el puente —\n"
                  f'   python -m nucleo.worker_bridge act use_tool \'{{"tool":"web_search","args":{{"query":"<qué buscas>"}}}}\'\n'
                  f"   (los precios y fichas suelen venir en los propios resultados). Si de verdad necesitas la "
                  f"página, cambia a un dominio que NO esté en la lista de bloqueados.")
    if res.get("hint"):
        print(f"⚠️ AVISO: {res['hint']}")
    print(f"URL: {res.get('url', '')}")
    if res.get("url_change"):
        # V2-293 — the DELTA, the only thing the worker cannot deduce: it has the current address, but not the
        # previous one. It goes NEXT TO the URL and before the elements because it is a consequence of the action
        # just performed, and the worker reads top to bottom. Measured: it wanted a MAXIMUM price of €150 and the
        # page switched to `min_sale_price=750` — the filter landed on another field and in the opposite direction,
        # without saying so.
        print(f"CAMBIÓ EN LA DIRECCIÓN: {res['url_change']} — es el filtro que la página ha aplicado DE VERDAD. "
              f"Si no es el que querías, deshazlo o vuelve a intentarlo; no sigas contando con el que pediste.")
    print(f"TÍTULO: {res.get('title', '')}")
    # V2-049 VISION: if there is a capture, tell the worker to LOOK at it with Read (the page as a human sees it)
    # and act by coordinates with click_at/type_at — the robust path for forms/date-pickers/selects.
    shot = res.get("shot")
    if shot and not _sees():
        # V2-289 — the model driving this session does NOT read images, so offering it the capture sends it to a
        # place from which it can only return empty-handed. Measured with DeepSeek taking over
        # (`search-buy-guitar__es`, 2026-08-24 11:23): it ran `Read` on the PNG and replied “The capture could not
        # be read (unsupported format). Continuing via DOM,” and again four steps later — a ~300–530 KB `Read` per
        # action to rediscover the same thing, plus a narration of the failure for the operator, who had no use for
        # it. The capture CONTINUES TO BE WRITTEN: it is what the operator sees in the browser card, and that
        # surface does not depend on who is driving.
        #
        # And it SAYS that it is unavailable instead of staying silent, because the text path is what remains and an
        # name is read as meaning the capture failed (which is something else, with its own warning just below).
        print("VISTA: no disponible para este modelo (no lee imágenes). Trabaja con los ELEMENTOS de abajo y "
              "usa click/type con su número [ref] — click_at/type_at piden coordenadas de una captura que no "
              "puedes mirar.")
    elif shot:
        vp = res.get("viewport") or {"width": 1280, "height": 800}
        print(f"VISTA (captura {vp['width']}×{vp['height']} px — MÍRALA con Read \"{shot}\" y actúa con "
              f"click_at/type_at usando las coordenadas en píxeles): {shot}")
    elif res.get("viewport"):
        # V2-205 — `look` EXISTS to produce a capture, so a `look` that returns none is not «nothing to say»: it
        # is a failure of the very thing that was asked for. `viewport` is what marks the answer as coming from
        # that command, so this cannot fire on a plain `snapshot`. Without the line the worker gets `ok` and
        # silence, which reads as success, and it loses the vision path without ever knowing.
        print("⚠️ AVISO: la captura no llegó a escribirse, así que NO hay vista que mirar en este paso. "
              "Sigue con los ELEMENTOS de abajo (camino de texto) o vuelve a intentar `look` tras navegar.")
    els = res.get("elements") or ""
    print("ELEMENTOS INTERACTIVOS (usa el número [ref] con click/type):\n" + (els or "(ninguno)"))


    # V2-212 — TWO RELATED COMMANDS WITH DIFFERENT SIGNATURES, and the worker mixed them up. Measured in
# `book-hotel-night-known__es` (2026-08-20 15:29):
#
#     Exit code 2 usage: nav_cli type_at [-h] [--submit] x y text
#     nav_cli type_at: error: argument y: invalid int value: 'Hotel Palacio de la Merced Burgos reservas 3'
#
# `type` takes a [ref] from the snapshot and `type_at` takes COORDINATES from the capture: it wrote the text where
# `y` belongs, exactly what happens when one command's arity is used with the other's name. And argparse's `usage`
# states the FORM but not the ERROR — the same kind of silent message as V2-203's `informe.json`: it says what
# failed and nothing about what to do, leaving the worker with nowhere to go.
_SCROLL_STEP = 800
# V2-219 — `scroll down` is what a worker writes, and it is not unreasonable: every other tool it has ever
# driven takes a direction there. Measured FOUR times across TWO unrelated cases the same day
# (`hotel-under-15-days` and the Bilbao round): `argument dy: invalid int value: 'down'`, Exit code 2, turn
# burned. Its own manual says `scroll 800`, so it KNOWS the syntax and does not use it — which is the signal
# that the syntax is the thing that is wrong, not the worker.
#
# Accepting the word is not a hardcoded verb table (the thing this repo refuses to build): nothing here is
# CLASSIFYING intent. The direction is already the argument; this only stops the CLI from rejecting the most
# natural way to write it.
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
    # worker wrote `nav_cli navigate` with NO ARGUMENT at 32 s, received only the `usage:`, and **wrote it again
    # without an argument 42 s later**; `visit` did the same. In the SAME session, bare `worker_bridge act` —which
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
    cuando escribe el comando. Medido en los logs de sesion del plato: `nav_cli type: error: argument ref:
    invalid int value: '[2]'`. Same rule as V2-306/V2-219: copying literally what we show it must not cost a turn.
    """
    return int(str(v).strip().strip("[]"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nav_cli", description="Conduce el navegador de zaelar (worker Claude Code)")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_GuidedParser)
    sub.add_parser("snapshot", help="estado + elementos interactivos de la página actual")
    sub.add_parser("look", help="VISIÓN: captura la página → ruta PNG para Read + coordenadas para click_at/type_at")
    # V2-306 — `open`/`goto` are ALIASES of navigate, and it is the CLI that was wrong, not the worker (the
    # V2-219 rule). Measured on `find-best-hotel-city__es` (2026-08-25 02:22): TWO workers in a row wrote
    # `nav_cli open <url>` — the natural verb, and the one our own recipe teaches in prose («para ABRIR una
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
    # V2-341 — TWO MORE FORMS THAT THE CLI REJECTED AND THE WORKER WRITES ON ITS OWN. Same rule as V2-306: when
    # the natural usage is unambiguous, the CLI is the one that is wrong. Measured across ALL test-rig session logs
    # (41 contract errors involving `nav_cli`):
    #
    #     18x  `open <url>`                    <- already closed by V2-306; the 18 are earlier
    #      5x  `nav_cli <url>` without a verb  <- a standalone URL can only be `navigate`
    #      5x  `type_at <ref> "text"`         <- confusing `type` (ref) with `type_at` (coordinates)
    #
    # The two cases closed here are NOT guesses about intent: a string beginning with http(s) cannot be any other
    # verb, and `type_at` with TWO arguments where the second is not a number can only be the usual `type` command.
    # Each costs a worker turn and, measured in the car round, five chained errors left the sheet empty.
    #
    # WATCH THE INDEX: `main(argv=None)` lets argparse read `sys.argv[1:]`, so the VERB is at position 0 here —
    # not 1. Writing it as `argv[1]` crashed on every real invocation and passed the tests, which pass a list.
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
    _print_state(res)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
