"""Showing pictures from a turn: the execution, shared by both channels (V2-457).

Third of the family, after `music_turn` (V2-380) and `video_turn` (V2-383), and built the same way for the same
reason: anything decided per-channel diverges per-channel. What is shared is the MECHANISM — search, load the
viewer, and report what actually happened — so voice and probe cannot drift into two different behaviours for
the same request.

WHY A FAST PATH AT ALL. Until today "conseguir una foto REAL para ENSEÑARLA" was a documented reason to
ESCALATE (the rule dates from a real 2026-08-03 incident where the brain asked `web_search` for a photo,
`web_search` can only return text, and the brain ended up DESCRIBING the picture in words for six turns). That
rule fixed the right bug with the only tool available at the time. It is no longer the only tool.

Measured on 2026-08-28, same request, both routes:

    Brain Worker (what the operator actually got)   355 s   $1.96   10 photos, Autocar India + mad4wheels
    Google Images through the warm Chromium           3.0 s  ~$0     cdn.ferrari.com originals, 3128x2333 master

The worker's work was genuinely good — it rejected a bot-blocked source, a paywalled one, and a set of URLs it
suspected were hallucinated. It simply never reached Ferrari's own gallery, because ferrari.com renders by JS
and its fetch saw an empty page. An image index had already crawled what the worker was paying a language model
to re-derive one page at a time.

So the DEFAULT flips: pictures are a light turn now. Escalation is not removed — it is where it always belonged,
which is CURATION. "Una foto del Amalfi" is a lookup. "Las fotos oficiales de prensa, verificadas, y dime de
qué fuente sale cada una" is research, and so is "no, esas no me valen" after a first set came back. The router
description draws that line; this module only executes the light half and reports honestly enough that the next
turn can escalate on the operator's word rather than on a guess.
"""
from __future__ import annotations

# How many pictures a set holds. Twelve fills the thumbnail strip without turning the viewer into a contact
# sheet, and it is what one Google results page yields without scrolling — asking for more would cost a second
# page load to add pictures nobody scrolls to.
DEFAULT_N = 12


def request_from(tool_calls: list) -> dict:
    """What `show_images` asked for, normalised: `{query, n}`."""
    si = next((t for t in (tool_calls or []) if t.get("name") == "show_images"), None) or {}
    args = si.get("args") or {}
    try:
        n = int(args.get("n") or DEFAULT_N)
    except Exception:  # noqa: BLE001
        n = DEFAULT_N
    return {"query": str(args.get("query") or "").strip(), "n": max(1, min(n, 24))}


async def execute(query: str, n: int = DEFAULT_N) -> dict:
    """Search the pictures and load the viewer; return the report of what HAPPENED, so the mouth need not guess.

    Same rail as everything else that puts something on the canvas (`brain_action` -> the widget's own
    `apply_action`), not a second way of showing pictures. Fail-soft end to end: the turn has to come out even
    if the browser is down, and when it is down the honest sentence is that we could not look, not that there
    are no photos.
    """
    q = str(query or "").strip()
    parte: dict = {"executed": "show_images", "query": q[:80], "ok": False, "count": 0}
    if not q:
        parte["message"] = "no dijiste de qué"
        return parte
    try:
        from nucleo import browser_search as _bs
        res = await _bs.images(q, n)
        res = res if isinstance(res, dict) else {}
        items = [it for it in (res.get("items") or []) if isinstance(it, dict) and it.get("url")]
        parte["source"] = str(res.get("source") or "")
        if res.get("degraded_from"):
            parte["degraded_from"] = str(res["degraded_from"])
        if res.get("blocked"):
            parte["blocked"] = True
        if not items:
            parte["message"] = str(res.get("error") or "")[:160] or "no encontré fotos de eso"
            # También la que volvió VACÍA — es exactamente la que hay que poder diagnosticar después.
            _evidence(parte)
            return parte
        from widgets.server_api import brain_action
        loaded = await brain_action("imagenes", "show",
                                    {"items": items, "query": q, "source": parte.get("source") or ""})
        loaded = loaded if isinstance(loaded, dict) else {}
        parte["ok"] = bool(loaded.get("ok"))
        parte["count"] = int(loaded.get("n") or 0)
        # THE CARD OPENS WHERE THE DATA LANDS (V2-463). The voice provider emits its own early `show` for
        # instant feedback, but this rail is shared with the probe channel - and there NOBODY emitted it, so a
        # whole measured round filled the viewer while the operator watched a canvas where no card ever
        # appeared (2026-08-28, `show-real-photo-of-a-new-car__es`: 12 photos in the store, nothing on
        # screen). Emitting on the shared rail instead of patching the second channel is the lesson this
        # codebase has now paid for five times. Idempotent on the frontend; only fires when something loaded.
        if parte["ok"] and parte["count"]:
            try:
                from voice.observer import emit as _emit
                _emit("widget", "show", extra={"id": "imagenes", "src": "flash"})
            except Exception:  # noqa: BLE001
                pass
        # WHERE the pictures come from is part of the answer, not decoration: the operator's own review of the
        # slow route praised it for going to the official site, so a fast route that cannot say whose picture
        # this is would be trading the thing he valued for speed.
        parte["sites"] = _sites(items)
        parte["first"] = str(items[0].get("title") or items[0].get("site") or "")[:120]
        if not parte["ok"]:
            parte["message"] = str(loaded.get("error") or "")[:160]
        _evidence(parte)
        return parte
    except Exception as e:  # noqa: BLE001
        parte["execute_error"] = str(e)[:200]
        _evidence(parte)
        return parte


def _evidence(parte: dict) -> None:
    """One observability line per SEARCH, with the query and where the photos came from.

    Exists because the round that produced dictionary pictures could not be diagnosed afterwards: the
    next `show` overwrote the widget store, so the junk query was simply GONE - the only trace was the
    spoken sentence naming spanishdict.com. What a search asked and what it got back is evidence of
    the turn, not state of the widget, and evidence is emitted the moment it exists (V2-463)."""
    try:
        from voice.observer import emit as _emit
        _emit("brain", "🖼️ fotos: búsqueda", role="system", extra={
            "cat": "flash", "query": str(parte.get("query") or ""), "ok": bool(parte.get("ok")),
            "count": int(parte.get("count") or 0), "source": str(parte.get("source") or ""),
            "sites": list(parte.get("sites") or []), "blocked": bool(parte.get("blocked")),
            "degraded_from": str(parte.get("degraded_from") or "")})
    except Exception:  # noqa: BLE001
        pass


def _sites(items: list) -> list:
    """The distinct publishers in a set, most-represented first — at most three, for a sentence to say aloud."""
    counts: dict[str, int] = {}
    for it in items:
        s = str((it or {}).get("site") or "").strip()
        if s:
            counts[s] = counts.get(s, 0) + 1
    return [s for s, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:3]


def spoken_for(parte: dict, ack: str) -> str:
    """What gets SAID after trying to show the pictures. `ack` is the language's canned line, for the mute case.

    The set is NAMED — how many, and whose — for the same reason the video player names the video it loaded
    (V2-057): it lets the operator verify at a glance that these are the pictures asked for, and it is the
    difference between delivering and claiming to have delivered. And when nothing loaded it says so, because a
    reassuring sentence over an empty card is the failure this family keeps relearning (V2-176, V2-209, V2-377,
    V2-380, V2-383).
    """
    parte = parte if isinstance(parte, dict) else {}
    if parte.get("executed") != "show_images":
        return ack
    if parte.get("ok"):
        n = int(parte.get("count") or 0)
        sites = [s for s in (parte.get("sites") or []) if s]
        de = f" de {', '.join(sites[:2])}" if sites else ""
        if n == 1:
            return f"Ya la tienes en pantalla{de}."
        return f"Te he puesto {n} fotos en pantalla{de} — dime si quieres ver alguna en concreto."
    if parte.get("blocked"):
        return "No he podido buscar las fotos ahora mismo: el buscador me ha bloqueado. Lo reintento si quieres."
    msg = str(parte.get("message") or parte.get("execute_error") or "").strip()
    return "No he podido enseñártelas: " + (msg or "no encontré fotos de eso.")


async def voice_turn(req: dict, *, silent: bool) -> "tuple[dict, str]":
    """`(parte, frase)` para el canal de VOZ — el cuerpo entero de su rama, aquí y no allí.

    Vive en este módulo por lo mismo que `video_turn.voice_dispatch`: el provider de voz es un fichero-dios con
    techo, y el trinquete pide extraer antes que subirlo. Además deja la resolución del idioma de este lado, así
    que el provider no gana otro import perezoso — que es la otra mitad de lo que el trinquete vigila.

    `silent` = el modelo no dijo nada en este turno. Solo entonces se habla: encajar el parte sobre una
    respuesta que ya existe la cuenta dos veces, y callar tras una tool deja al turno siguiente creyendo que la
    petición sigue sin atender.
    """
    parte = await execute(req.get("query") or "", req.get("n") or DEFAULT_N)
    if not silent:
        return parte, ""
    try:
        from voice.engine.core import langs
        ack = langs.current_language().data_ack
    except Exception:  # noqa: BLE001 — sin idioma resoluble se dice el parte igual, que es lo que importa
        ack = ""
    return parte, spoken_for(parte, ack)
