"""oauth_callback.py — the page every OAuth door returns to, and the SIGNAL it sends back (V2-700).

Five connectors each hand-rolled this page (`calendar`, `photos`, `video`, `files`, `contacts`). They
looked alike and behaved alike, and all five had the same defect: the page told the operator it had worked
and then **told the card nothing**. So the widget that opened the window went on showing «Conectar» until
something else happened to refresh it, and the operator's own report is the proof this matters:

> «Cuando volvemos a la pantalla de nuestro agente personal ya automáticamente desaparece la opción de
> conectar y se marca como conectado. Eso sigue sin suceder […] Si no, el usuario está confundido y podría
> volver a iniciar indefinidamente la conexión.»

## The signal

This page is OURS and it runs in a window WE opened, so it can talk to its opener directly:

    window.opener.postMessage({zaelar: "connector", family, provider, ok}, "*")

⚠️ **`"*"` is deliberate and it is safe HERE, in this direction.** The engine serves two local origins
(`127.0.0.1:43917` and `local.zaelar.com:44317`) and the callback is normalized onto loopback, so the
opener is frequently on the OTHER one — naming a single target origin would silently drop the message in
exactly the case it is needed. What travels is three flags and no secret: the worst a listener could learn
is that a connection finished, which it is about to learn anyway.

**The receiving side is where the check belongs**, and it is a real one: `desktop.js` accepts this message
only from its own origin or a loopback one, and treats it as a HINT — it re-reads the state from the engine
rather than believing the flag. A forged message therefore buys a refresh and nothing else.

Belt and braces on purpose: the message can be lost (opener gone, window reused, a mobile tab with no
opener at all), so the canvas also watches for the window closing and polls within a bounded window. One
signal that usually fires instantly, one that always eventually fires.
"""
from __future__ import annotations

import html
import json

#: Seconds the page waits before closing itself. Long enough to be read, short enough not to be litter.
_CLOSE_AFTER_MS = 2500


def page(ok: bool, detail: str, *, family: str, provider: str = "", label: str = "",
         done: str = "", close_after_ms: int = _CLOSE_AFTER_MS) -> str:
    """The callback page, identical for every door.

    `family` is the widget family this connection belongs to (`agenda`, `contactos`, `fotos`, `video`,
    `archivos`) — the canvas routes the refresh by it. `label` names the service to the operator; `done`
    overrides the success sentence when a connector has something more useful to say.
    """
    label = label or "La cuenta"
    title = f"{label} conectado" if ok else "No se pudo conectar"
    icon = "✅" if ok else "⚠️"
    body = (done or "Ya puedes volver a la tarjeta de zaelar. Esta ventana se cierra sola.") if ok else \
        f"Detalle: {detail}. Cierra esta ventana e inténtalo de nuevo desde la tarjeta."
    msg = json.dumps({"zaelar": "connector", "family": family, "provider": provider, "ok": bool(ok)})
    return (
        "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:system-ui,-apple-system,sans-serif;background:#0f1115;color:#e6e6e6;"
        "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}"
        ".c{max-width:28rem;text-align:center;padding:2rem}h1{font-size:1.3rem;margin:.5rem 0}"
        "p{color:#9aa0aa;line-height:1.5}</style></head><body><div class='c'>"
        f"<div style='font-size:3rem'>{icon}</div><h1>{html.escape(title)}</h1>"
        f"<p>{html.escape(body)}</p>"
        "<script>(function(){try{"
        # The opener is told FIRST and unconditionally — before the close timer, and even on failure, so a
        # card that opened this window stops waiting instead of sitting on «Abriendo…» forever.
        f"if(window.opener&&!window.opener.closed){{window.opener.postMessage({msg},'*');}}"
        "}catch(e){}"
        f"setTimeout(function(){{try{{window.close()}}catch(e){{}}}},{int(close_after_ms)});"
        "})()</script>"
        "</div></body></html>"
    )


#: Which widget card each connector family is shown through. The canvas refreshes BY WIDGET ID, so this is
#: the translation between «a Google account was linked» and «that card is now stale».
FAMILY_WIDGET = {"agenda": "agenda", "contactos": "contactos", "fotos": "fotos",
                 "video": "youtube", "archivos": "archivos", "musica": "musica"}


def announce(family: str) -> None:
    """Tell the canvas that this family's connection state CHANGED (V2-700).

    ⚠️ This is the path that already worked for everything else and that OAuth was missing. A widget's own
    store goes through `widgets/store.py::save`, which emits ONE `widget/data` event and makes the open card
    re-fetch and re-render itself — which is why the messaging card notices a Telegram QR being scanned with
    no polling anywhere. OAuth tokens live in `SecureJsonStore`, NOT in a widget store, so linking an
    account changed nothing the canvas could see: the card went on offering «Conectar» until something
    unrelated happened to refresh it.

    Emitting the same event here closes that gap for every card of the family at once — including one the
    operator never pressed the button in, and the Connectors tab.

    Never raises: a notification that fails must not turn a successful connection into an error.
    """
    wid = FAMILY_WIDGET.get((family or "").strip().lower())
    if not wid:
        return
    try:
        from voice.observer import emit
        emit("widget", "data", extra={"id": wid, "src": "connector"})
    except Exception:  # noqa: BLE001 — see the docstring
        pass
