"""V2-700 — connecting an account, and the card NOTICING.

The operator connected Google Contacts and reported two things:

> «El conector de Google esta vez se ha abierto en una pestaña nueva en lugar de en un pop-up. […] no me ha
> gustado en la versión desktop que se me cambie de pestaña. Era mejor ayer cuando lo probé desde la agenda
> […] y idealmente, cosa que no está sucediendo todavía, cuando volvemos a la pantalla de nuestro agente
> personal ya automáticamente desaparece la opción de conectar y se marca como conectado. Eso sigue sin
> suceder y se tiene que estar detectando en tiempo real. […] Si no, el usuario está confundido y podría
> volver a iniciar indefinidamente la conexión.»

MEASURED: five connectors had five hand-rolled copies of the same callback page, and every one of them told
the OPERATOR it had worked while telling the CARD nothing. The messaging card already notices a Telegram QR
being scanned with no polling at all — because its store goes through `widgets/store.py::save`, which emits
one `widget/data` event. OAuth tokens live in a `SecureJsonStore`, which emits nothing, so linking an
account changed nothing the canvas could see.

This file holds the server half. The browser half (the popup features, the listener, the button going
quiet) is `tests/browser/unit/widgets/test_connecting_an_account_is_noticed_in_real_time.py`.
"""
from __future__ import annotations

import json
import re

import pytest

from connectors import oauth_callback as ocb

DOORS = ["calendar", "photos", "video", "files", "contacts"]


def _page_of(mod_name: str):
    mod = __import__(f"connectors.{mod_name}.server_api", fromlist=["_page"])
    return mod._page


# ── the page every door returns to ──────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("door", DOORS)
def test_every_oauth_door_returns_the_SAME_page(door):
    """Five copies drifted into two behaviours — a popup in the agenda, a whole tab in contacts — and all
    five shared one defect. One builder is what stops the next one from drifting too."""
    html = _page_of(door)(True, "")
    assert "postMessage" in html, f"{door}'s callback tells the card nothing"
    assert "window.opener" in html


@pytest.mark.parametrize("door,family", list(zip(DOORS, ["agenda", "fotos", "video", "archivos", "contactos"])))
def test_the_page_names_the_family_the_canvas_routes_by(door, family):
    html = _page_of(door)(True, "")
    payload = json.loads(re.search(r"postMessage\((\{.*?\}),'\*'\)", html).group(1))
    assert payload == {"zaelar": "connector", "family": family, "provider": "", "ok": True}


def test_a_FAILED_connection_also_tells_the_card():
    """Otherwise a card that opened the window sits on «Abriendo Google…» forever, which is the same
    confusion he reported, only with the opposite cause."""
    html = ocb.page(False, "el usuario canceló", family="contactos")
    payload = json.loads(re.search(r"postMessage\((\{.*?\}),'\*'\)", html).group(1))
    assert payload["ok"] is False
    assert "postMessage" in html[:html.index("setTimeout")], "the opener is told BEFORE the close timer"


def test_the_page_escapes_what_it_shows():
    """`detail` carries a provider's error string straight onto a page we serve."""
    html = ocb.page(False, "<img src=x onerror=alert(1)>", family="contactos")
    assert "<img src=x" not in html
    assert "&lt;img" in html


def test_the_message_carries_no_secret():
    """It is posted with targetOrigin "*" on purpose — the callback is normalized onto loopback while the
    card is often on the other listener, so naming one origin drops it exactly when it is needed. That is
    only safe while the payload is three flags."""
    html = ocb.page(True, "", family="agenda", provider="google")
    payload = json.loads(re.search(r"postMessage\((\{.*?\}),'\*'\)", html).group(1))
    assert set(payload) == {"zaelar", "family", "provider", "ok"}
    assert all(not isinstance(v, (dict, list)) for v in payload.values())
    assert "token" not in html.lower() and "secret" not in html.lower()


# ── the event the canvas actually listens to ────────────────────────────────────────────────────────────

def test_linking_an_account_emits_the_same_event_a_widget_store_does(monkeypatch):
    """This is the path that already worked for everything else. `widgets/store.py::save` emits ONE
    `widget/data` event and the open card re-fetches itself — which is why messaging notices a QR scan with
    no polling. OAuth wrote to a SecureJsonStore instead, so it emitted nothing at all."""
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda kind, label, extra=None: seen.append((kind, label, extra)))
    ocb.announce("contactos")
    assert seen == [("widget", "data", {"id": "contactos", "src": "connector"})]


def test_every_family_resolves_to_a_real_widget():
    """A family whose widget id is wrong emits an event nobody is listening for — a refresh that silently
    never happens, which is indistinguishable from the bug this fixes."""
    import pathlib
    engine = pathlib.Path(__file__).resolve().parents[3]
    for family, wid in ocb.FAMILY_WIDGET.items():
        assert (engine / "widgets" / wid / "manifest.json").exists(), f"{family} → {wid} is not a widget"


def test_an_unknown_family_is_a_no_op_and_never_raises(monkeypatch):
    seen = []
    import voice.observer as obs
    monkeypatch.setattr(obs, "emit", lambda *a, **k: seen.append(a))
    ocb.announce("nope")
    ocb.announce("")
    ocb.announce(None)
    assert seen == []


def test_a_broken_observer_does_not_break_a_good_connection(monkeypatch):
    """A notification that fails must not turn a successful link into an error page."""
    import voice.observer as obs

    def boom(*a, **k):
        raise RuntimeError("observer down")

    monkeypatch.setattr(obs, "emit", boom)
    ocb.announce("agenda")          # must not raise


# ── the routes ──────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("door", DOORS)
def test_the_callback_route_announces_only_on_SUCCESS(door):
    """A refused exchange must not tell the canvas that something landed — the card would refresh, find
    nothing changed, and the operator would be left with a green page over an unlinked account."""
    import inspect
    mod = __import__(f"connectors.{door}.server_api", fromlist=["callback"])
    src = inspect.getsource(mod.callback)
    assert "_ocb.announce(" in src, f"{door} never tells the canvas"
    assert 'if res.get("ok")' in src, f"{door} announces regardless of the outcome"


@pytest.mark.parametrize("door", DOORS)
def test_disconnecting_announces_too(door):
    """Unlinking is a state change: a card that goes on saying «conectado» is the same lie in reverse."""
    import inspect
    mod = __import__(f"connectors.{door}.server_api", fromlist=["disconnect"])
    assert "_ocb.announce(" in inspect.getsource(mod.disconnect)
