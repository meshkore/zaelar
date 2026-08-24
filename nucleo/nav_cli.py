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

import argparse
import json
import os
import sys
import urllib.request

from nucleo import bridge_usage

_BASE = os.getenv("ZAELAR_BASE", "http://localhost:43917").rstrip("/")


#: How long we wait for one browser action before giving up on the ANSWER (not on the action). The error
#: message NAMES this number, so it lives once: two literals drift and then the hint states a wrong figure.
# El navegador es una CONEXIÓN DIRECTA: una acción que funciona, funciona en segundos. Medido contra el
# plató vivo sobre un sitio real: `navigate` 4,2 s · `look` 4,2 s · `extract` 0,05 s. Estaba en 90 —veinte
# veces el coste real— y eso no es «margen de sobra»: es que un cuelgue se lleva un tercio de la ronda antes
# de que nadie se entere. Medido el 2026-08-24 en `search-buy-guitar__es`: 90 de 250 segundos en un `type`
# que YA HABÍA ESCRITO el texto. Norma del operador el mismo día: «no tiene tiempos de espera de noventa
# segundos bajo ningún concepto». 25 s sigue siendo seis veces el coste real; lo que no da es para esconder
# un cuelgue.
_ACT_TIMEOUT_S = 25


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
    """¿El modelo que conduce esta sesión lee imágenes? Lo declara el escalón que la sirve
    (`nucleo/workers/providers.vision_env`) y llega por entorno, que es lo que este CLI hereda del worker.

    **Ausente = sí**, la conducta de siempre: un «no ve» equivocado deja ciego a un worker que veía, y eso es un
    fallo mudo; un «sí ve» equivocado cuesta un `Read` fallido y se sigue por el DOM."""
    return (os.environ.get("ZAELAR_NAV_VISION") or "").strip().lower() not in ("0", "false", "no")


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
        # V2-213: y CUÁL. «Prueba otro sitio» sin nombrar uno es un deseo; el que se atasca es el que no sabe a
        # dónde ir. Se listan ya excluido el host que acaba de bloquear.
        for _a in (res.get("wall_alts") or [])[:3]:
            print(f"   → prueba en {_a.get('name', '')}: {_a.get('url', '')}")
    if res.get("hint"):
        print(f"⚠️ AVISO: {res['hint']}")
    print(f"URL: {res.get('url', '')}")
    if res.get("url_change"):
        # V2-293 — el DELTA, que es lo único que el worker no puede deducir: la dirección de ahora la tiene, la
        # de antes no. Va JUNTO a la URL y antes de los elementos porque es una consecuencia de la acción que
        # acaba de hacer, y el worker lee de arriba abajo. Medido: quiso precio MÁXIMO 150 € y la página se fue
        # a `min_sale_price=750` — el filtro cayó en otro campo y en otro sentido, sin que nada lo dijera.
        print(f"CAMBIÓ EN LA DIRECCIÓN: {res['url_change']} — es el filtro que la página ha aplicado DE VERDAD. "
              f"Si no es el que querías, deshazlo o vuelve a intentarlo; no sigas contando con el que pediste.")
    print(f"TÍTULO: {res.get('title', '')}")
    # V2-049 VISIÓN: si hay captura, dile al worker que la MIRE con Read (la página como la ve un humano) y actúe
    # por coordenadas con click_at/type_at — el camino robusto para formularios/date-pickers/selects.
    shot = res.get("shot")
    if shot and not _sees():
        # V2-289 — el modelo que conduce esta sesión NO lee imágenes, así que ofrecerle la captura es mandarle a
        # un sitio del que solo puede volver con las manos vacías. Medido con el relevo a DeepSeek puesto
        # (`search-buy-guitar__es`, 2026-08-24 11:23): hizo `Read` de la PNG y contestó «La captura no se pudo
        # leer (formato no soportado). Sigo por DOM», y otra vez cuatro pasos después — un `Read` de ~300-530 KB
        # por acción para redescubrir lo mismo, más la narración del fallo al operador, que no tiene qué hacer
        # con ella. La captura SE SIGUE ESCRIBIENDO: es lo que el operador ve en la tarjeta del navegador, y esa
        # superficie no depende de quién conduzca.
        #
        # Y se DICE que no la hay en vez de callar, porque el camino de texto es el que queda y una ausencia sin
        # nombre se lee como que la captura falló (que es otra cosa, y tiene su propio aviso justo abajo).
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


# V2-212 — DOS COMANDOS HERMANOS CON FIRMAS DISTINTAS, y el worker mezcló las dos. Medido en
# `book-hotel-night-known__es` (2026-08-20 15:29):
#
#     Exit code 2 usage: nav_cli type_at [-h] [--submit] x y text
#     nav_cli type_at: error: argument y: invalid int value: 'Hotel Palacio de la Merced Burgos reservas 3'
#
# `type` toma un [ref] del snapshot y `type_at` toma COORDENADAS de la captura: escribió el texto donde va `y`,
# que es exactamente lo que sale de usar la aridad de uno con el nombre del otro. Y el `usage` de argparse dice
# la FORMA pero no el ERROR — la misma clase de mensaje mudo que el `informe.json` de V2-203: dice qué falló y
# nada de qué hacer, así que el worker no tiene de dónde tirar.
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
    return ""


# Un `usage` dice la FORMA; esto añade QUÉ hacer. Es el contrato del nodo 4.20 aplicado a los argumentos: lo que
# el puente sabe, lo dice — y un fallo dice además cómo se sale de él. El mecanismo se comparte (V2-219); lo que
# es de este puente es `_hint_for`.
_GuidedParser = bridge_usage.guided(_hint_for)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nav_cli", description="Conduce el navegador de zaelar (worker Claude Code)")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_GuidedParser)
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
    s = sub.add_parser("scroll", help="desplazar (píxeles, o `down`/`up`)")
    s.add_argument("dy", type=_scroll_amount, nargs="?", default=_SCROLL_STEP)
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
