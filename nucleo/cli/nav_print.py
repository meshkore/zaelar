"""nucleo/cli/nav_print.py — how `cli.nav` PRINTS the bridge's answer for the worker: the page state, the wall,
the hint, the view, and the way out of a known error. Public face: `nucleo.cli.nav`."""
from __future__ import annotations

import json
import os


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
    for aguja, salida in _m._QUE_HACER:
        if aguja in low:
            return salida
    return ""


def _print_state(res: dict) -> None:
    if not res.get("ok"):
        _err = str(res.get("error") or res.get("msg") or "desconocido")
        _sal = _m._salida(_err)
        print("ERROR: " + _err + (f" · {_sal}" if _sal else ""))
        return
    if "listings" in res:
        print(json.dumps(res.get("listings", []), ensure_ascii=False, indent=2))
        if (res.get("door") or {}).get("note"):          # the sheet's door turned rows away: say which and why
            print(f"⚠️ SHEET: {res['door']['note']}")
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
                  f'   python -m nucleo.cli.bridge act use_tool \'{{"tool":"web_search","args":{{"query":"<qué buscas>"}}}}\'\n'
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
    if shot and not _m._sees():
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


# At the bottom, not the top: `python -m nucleo.cli.nav` runs as `__main__`, so importing `nav` here first
# would re-import it while this module is still half-built.
from nucleo.cli import nav as _m  # noqa: E402
