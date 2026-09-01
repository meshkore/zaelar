"""V2-543 — messaging is voice-navigable: the VIEW is a declared action, and the manifest declares
every action apply_action handles.

Born from a live session (2026-09-01 18:39): «ve a la lista principal de los mensajes» and «muéstrame la
lista general» each got a bare `show_widget` and «Aquí lo tienes» over an unmoved screen — the platform
lens was widget.js-local state the voice could not touch, `close` was implemented but undeclared, and
the manifest carried 5 of the 12 actions data.py handled. The generator's manifest↔apply_action sync gate
SKIPS `backed` widgets on purpose (the supervisor owns that contract), so THIS file is that gate for
mensajeria: without it the drift that caused the incident can silently return.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

ENGINE = pathlib.Path(__file__).resolve().parents[4]


@pytest.fixture
def msg(tmp_path, monkeypatch):
    """ISOLATED store — never the operator's real inbox."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data as d
    return d


def _as_the_canvas_sends_it(payload):
    """`desktop.js` builds EVERY action payload as `{...payload, q}` (node 4.95)."""
    return {**payload, "q": ""}


def _manifest():
    return json.loads((ENGINE / "widgets" / "mensajeria" / "manifest.json").read_text(encoding="utf-8"))


def _seed(msg, monkeypatch=None):
    from connectors.messaging import store as ms
    ms.upsert_items("whatsapp", [
        {"messageId": "w1", "chatId": "111", "senderId": "111", "from": "JOSE VICENTE",
         "senderName": "JOSE VICENTE", "isGroup": False, "body": "[image received]",
         "urgencia": "media", "dirigido_a_mi": True},
        {"messageId": "w2", "chatId": "111", "senderId": "111", "from": "JOSE VICENTE",
         "senderName": "JOSE VICENTE", "isGroup": False, "body": "hola",
         "urgencia": "media", "dirigido_a_mi": True},
    ])
    ms.upsert_items("email", [
        {"messageId": "42", "chatId": "a@b.com", "senderId": "a@b.com", "from": "Ana",
         "senderName": "Ana", "isGroup": False, "body": "[Asunto: factura]\nadjunto",
         "urgencia": "media", "dirigido_a_mi": False, "subject": "factura", "msgid": "<i@d>"},
    ])
    return ms


# ── The manifest IS the vocabulary — the gate the backed kind skips ─────────────────────────────────────────

def test_the_manifest_declares_every_action_apply_action_handles():
    """The incident's root: read/dismiss/clear/open/close/readchat/connect/disconnect were handled and
    invisible. Parse the comparisons in data.py and demand a 1:1 match with the declared vocabulary."""
    src = (ENGINE / "widgets" / "mensajeria" / "data.py").read_text(encoding="utf-8")
    handled = set(re.findall(r'action\s*==\s*"([a-z_]+)"', src))
    for group in re.findall(r'action\s+in\s+\(([^)]*)\)', src):
        handled |= set(re.findall(r'"([a-z_]+)"', group))
    declared = set(_manifest()["actions"])
    # connect/disconnect stay undeclared ON PURPOSE: they carry credentials, and the door for the voice is
    # open_connectors (V2-520: the voice transports intent, never a credential).
    assert handled - {"connect", "disconnect"} == declared, (
        f"handled-but-invisible: {sorted(handled - {'connect', 'disconnect'} - declared)} · "
        f"declared-but-dead: {sorted(declared - handled)}")


def test_trash_is_confirm_gated_and_archive_is_not():
    acts = _manifest()["actions"]
    assert acts["trash"].get("confirm") is True, "deleting in the REAL mailbox must ask first"
    assert not acts["archive"].get("confirm"), "archiving is recoverable — no gate"


# ── show_view: pushes with a witness counter, answers, and expires ──────────────────────────────────────────

def test_show_view_pushes_a_moving_token_and_ANSWERS_with_the_matching_chats(msg):
    _seed(msg)
    r = msg.apply_action("show_view", _as_the_canvas_sends_it({"platform": "whatsapp"}))
    assert r["ok"] and r["view"]["platform"] == "whatsapp" and r["view"]["n"] == 1
    assert r["result"]["count"] == 1 and r["result"]["chats"][0]["name"] == "JOSE VICENTE"
    r2 = msg.apply_action("show_view", _as_the_canvas_sends_it({"platform": "whatsapp"}))
    assert r2["view"]["n"] == 2, "asking for the same view twice must still move the token"


def test_the_spoken_aliases_land_on_the_main_list(msg):
    _seed(msg)
    for word in ("all", "todo", "principal", "general", ""):
        r = msg.apply_action("show_view", _as_the_canvas_sends_it({"platform": word}))
        assert r["ok"] and r["view"]["platform"] == "", word
    assert r["result"]["count"] == 2


def test_an_unknown_view_is_an_error_that_teaches_the_retry_shape(msg):
    _seed(msg)
    r = msg.apply_action("show_view", _as_the_canvas_sends_it({"platform": "instagram"}))
    assert r["ok"] is False and "show_view" in r["error"] and "platform" in r["error"]


def test_show_view_exits_an_open_thread(msg):
    """«Vuelve a la lista principal» said from inside a chat has to actually LEAVE the chat."""
    _seed(msg)
    msg.apply_action("open", _as_the_canvas_sends_it({"name": "jose vicente"}))
    assert msg.view_data()["active_chat"] is not None
    msg.apply_action("show_view", _as_the_canvas_sends_it({"platform": "all"}))
    assert msg.view_data()["active_chat"] is None


def test_a_stale_view_expires_server_side(msg):
    _seed(msg)
    msg.apply_action("show_view", _as_the_canvas_sends_it({"platform": "email"}))
    db = msg.load_db()
    db["view"]["at"] -= msg._VIEW_TTL_S + 1
    msg.store.save(msg.WIDGET_ID, db)
    assert msg.view_data()["view"] is None, "a pushed lens kept forever yanks next week's reopen"


# ── open by NAME ────────────────────────────────────────────────────────────────────────────────────────────

def test_open_accepts_the_spoken_name_accent_and_case_insensitive(msg):
    _seed(msg)
    r = msg.apply_action("open", _as_the_canvas_sends_it({"name": "josé vicente"}))
    assert (r.get("active_chat") or {}).get("chatId") == "111"


def test_open_with_an_unknown_name_teaches_instead_of_guessing(msg):
    _seed(msg)
    r = msg.apply_action("open", _as_the_canvas_sends_it({"name": "nadie"}))
    assert r["ok"] is False and "open" in r["error"]
    assert msg.view_data()["active_chat"] is None


# ── archive/trash: the order leaves the widget AND travels to the real app ──────────────────────────────────

def test_archive_is_email_only_and_enqueues_for_the_connector(msg):
    ms = _seed(msg)
    items = msg.view_data()["items"]
    wa_n = next(i["n"] for i in items if i["platform"] == "whatsapp")
    bad = msg.apply_action("archive", _as_the_canvas_sends_it({"n": wa_n}))
    assert bad["ok"] is False and "EMAIL" in bad["error"]
    em_n = next(i["n"] for i in msg.view_data()["items"] if i["platform"] == "email")
    ok = msg.apply_action("archive", _as_the_canvas_sends_it({"n": em_n}))
    assert ok["ok"] and ok["result"]["action"] == "archive"
    q = ms.take_pending_disposal("archive")
    assert q and q[0]["platform"] == "email" and q[0]["messageId"] == "42"
    assert not any(i["platform"] == "email" for i in msg.view_data()["items"]), "the item must leave the widget"


def test_trash_enqueues_its_own_queue_not_the_archive_one(msg):
    ms = _seed(msg)
    em_n = next(i["n"] for i in msg.view_data()["items"] if i["platform"] == "email")
    msg.apply_action("trash", _as_the_canvas_sends_it({"n": em_n}))
    assert ms.take_pending_disposal("archive") == []
    q = ms.take_pending_disposal("trash")
    assert q and q[0]["messageId"] == "42"
