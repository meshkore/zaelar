"""Asking to connect a channel must LAND on the form (V2-520).

Reported live by the operator 2026-08-31: "conéctame el correo" opened the messaging card and nothing
else — no dialog, no question about which mail provider. Everything they asked for already existed
(`connectors/email/providers.py` ships Gmail and Outlook/Hotmail with OAuth, and the connect form has a
provider picker); it was simply UNREACHABLE:

  · the channels panel is local `widget.js` state (`_connectorsOpen`) that only the header button could
    flip, and `showChannels = _connectorsOpen || connectedCount===0` — with WhatsApp/Telegram already
    connected the card renders the MESSAGE list, forever;
  · `apply_action` had handled `connect` for a long time, but the manifest never DECLARED it, and an
    action that is not declared is invisible to the brain (the widget contract says so in as many words).

So the fix is a declared intent, `open_connectors`, that carries a timestamped `connect_focus` in the
widget's own data — never a credential, because a password or an OAuth round-trip is not something to
conduct by voice.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parents[4] / "widgets" / "mensajeria" / "manifest.json"
WIDGET_JS = MANIFEST.with_name("widget.js")


@pytest.fixture
def data(tmp_path, monkeypatch):
    """Point the widget store at a temp dir — a unit test never touches the operator's real messages."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data as mod
    return mod


def test_the_brain_can_SEE_the_action(data):
    """A data-op the manifest does not declare is invisible to the brain — the whole reason this failed."""
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "open_connectors" in (man.get("actions") or {})
    assert man.get("usage"), "the brain needs to be told WHEN to use it, not just that it exists"
    assert "conect" in man["usage"].lower()


def test_asking_to_connect_email_focuses_the_email_form(data):
    out = data.apply_action("open_connectors", {"platform": "email"})
    focus = out.get("connect_focus")
    assert focus and focus["platform"] == "email" and focus["ts"] > 0


def test_the_request_SURVIVES_a_repaint(data):
    """`view_data` runs on every render; consuming the request on read would lose it on the first repaint."""
    data.apply_action("open_connectors", {"platform": "email"})
    assert (data.view_data().get("connect_focus") or {}).get("platform") == "email"
    assert (data.view_data().get("connect_focus") or {}).get("platform") == "email"


def test_an_unknown_platform_still_opens_the_panel(data):
    """«conéctame una cosa» → show the catalogue rather than refusing: the panel IS the answer."""
    out = data.apply_action("open_connectors", {"platform": "señales de humo"})
    assert out["connect_focus"]["platform"] == ""


def test_the_intent_never_carries_a_credential(data):
    """Opening a form is not connecting. A password or an OAuth round-trip is never done by voice."""
    out = data.apply_action("open_connectors", {"platform": "email", "email_password": "hunter2"})
    assert "hunter2" not in json.dumps(out)
    db = data.load_db()
    assert not db.get("pending_control"), "opening the panel must not enqueue a connection"


def test_the_widget_honours_a_request_ONCE():
    """Honouring it on every repaint would re-open the panel the operator just closed — a new message
    arriving would be enough. The guard is the remembered timestamp.

    Source-level only, and deliberately paired with the RENDER check (`render_connect_panel.py`, a live
    node): grepping this file proves the guard was written, never that it runs — an earlier version of
    this test passed happily against `if(false && focus …)`, because the string was still there. What
    proves the behaviour is the render."""
    src = WIDGET_JS.read_text(encoding="utf-8")
    assert "_focusDone" in src and "_connectorsOpen = true" in src
