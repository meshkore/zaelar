"""V2-611 — the review-first reply: `draft` writes into a visible box, `send_draft` is the separate,
deliberate act that actually sends. Built after diagnosing that the previous target resolution for a
NO-active-chat reply (`reply`'s own fallback, unchanged here) addressed CHAT numbering, which the flat
EMAIL list never has — the exact ambiguity `_resolve_target` closes by accepting `messageId` too.
"""
from __future__ import annotations

import pytest

from widgets import store
from widgets.mensajeria import data as msg

_EMAIL = {"n": 1, "platform": "email", "chatId": "ana@x.com", "messageId": "uid-1", "senderId": "ana@x.com",
          "from": "Ana", "subject": "Reunión", "msgid": "<m1>", "dir": "in", "body": "¿Confirmamos?", "ts": 1}
_EMAIL2 = {"n": 2, "platform": "email", "chatId": "banco@x.com", "messageId": "uid-2", "senderId": "banco@x.com",
           "from": "Banco", "subject": "Extracto", "msgid": "<m2>", "dir": "in", "body": "Adjunto", "ts": 2}
_WA = {"n": 3, "platform": "whatsapp", "chatId": "34600", "messageId": "wa-1", "senderId": "34600",
       "from": "Marta", "dir": "in", "body": "¿Vienes?", "ts": 3}


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(store, "_last_hash", {})


def _seed(items):
    db = msg.load_db()
    db["items"] = list(items)
    store.save(msg.WIDGET_ID, db)


# ── _resolve_target: the identity bug this closes ────────────────────────────────────────────────────────

def test_n_addresses_the_flat_email_list_directly_not_a_chat_number(sandbox):
    """The bug: `reply`'s old fallback resolved `n` against `_group_chats`' OWN numbering. Two single-message
    email chats renumber identically to two flat items (1, 2 either way) here, so this alone would not have
    caught it — the real proof is `test_email_and_chat_numbering_can_legitimately_differ` below."""
    _seed([_EMAIL, _EMAIL2])
    db = msg.load_db()
    t = msg._resolve_target(db, n=2)
    assert t is not None and t["messageId"] == "uid-2"


def test_email_and_chat_numbering_can_legitimately_differ(sandbox):
    """Two messages from the SAME sender collapse into ONE chat — so item n=2 (second message) is chat n=1
    (only chat), not chat n=2. Resolving item `n` against chat numbering would silently reply to nothing, or
    to the wrong sender, on a flat list that has no chats at all in its own UI."""
    same_sender_2 = {**_EMAIL2, "n": 2, "chatId": "ana@x.com", "messageId": "uid-2b", "senderId": "ana@x.com"}
    _seed([_EMAIL, same_sender_2])
    db = msg.load_db()
    t = msg._resolve_target(db, n=2)
    assert t is not None and t["messageId"] == "uid-2b"          # NOT resolved as "chat n=2" (there is none)


def test_n_resolves_even_when_items_carry_no_stored_n_at_all(sandbox):
    """Real storage NEVER persists `n` on an item — it exists only once `_renumber` assigns it (data.py:128),
    the same way read/dismiss/archive/trash/hide already rely on it. Every other test in this file seeds
    items WITH a literal `n` for readability, which would hide a resolver that forgot to renumber first (it
    did, once): this one seeds the REAL shape, with no `n` key present anywhere."""
    bare = [{k: v for k, v in it.items() if k != "n"} for it in (_EMAIL, _EMAIL2)]
    _seed(bare)
    db = msg.load_db()
    t = msg._resolve_target(db, n=2)
    assert t is not None and t["messageId"] == "uid-2"


def test_messageId_resolves_unambiguously_regardless_of_n(sandbox):
    _seed([_EMAIL, _EMAIL2])
    db = msg.load_db()
    t = msg._resolve_target(db, mid="uid-2")
    assert t is not None and t["n"] == 2


def test_an_open_thread_with_no_n_targets_its_last_message(sandbox):
    _seed([_WA])
    db = msg.load_db()
    db["active_chat"] = {"platform": "whatsapp", "chatId": "34600"}
    store.save(msg.WIDGET_ID, db)
    db = msg.load_db()
    t = msg._resolve_target(db)
    assert t is not None and t["messageId"] == "wa-1"


def test_an_open_thread_already_fully_answered_still_has_an_identity(sandbox):
    """V2-546: replying must not require an unread message to exist. With nothing left in `items` for this
    chat, the conversation's own platform/chatId are still enough to address a reply to."""
    _seed([])
    db = msg.load_db()
    db["active_chat"] = {"platform": "whatsapp", "chatId": "34600"}
    store.save(msg.WIDGET_ID, db)
    db = msg.load_db()
    t = msg._resolve_target(db)
    assert t == {"platform": "whatsapp", "chatId": "34600"}


def test_no_target_and_no_open_thread_resolves_to_nothing(sandbox):
    _seed([])
    assert msg._resolve_target(msg.load_db()) is None


# ── draft / send_draft ───────────────────────────────────────────────────────────────────────────────────

def test_a_draft_is_visible_before_anything_sends(sandbox):
    _seed([_EMAIL])
    r = msg.apply_action("draft", {"n": 1, "text": "Sí, a las 10 nos va bien"})
    assert r["ok"] and r["text"] == "Sí, a las 10 nos va bien"
    d = msg.view_data()
    assert d["draft"]["text"] == "Sí, a las 10 nos va bien"
    assert d["draft"]["target"]["messageId"] == "uid-1"
    assert d["items"], "un draft NUNCA envía por sí solo — el mensaje sigue pendiente"


def test_send_draft_sends_exactly_the_boxs_current_text(sandbox):
    _seed([_EMAIL])
    msg.apply_action("draft", {"n": 1, "text": "borrador a medias"})
    msg.apply_action("draft", {"n": 1, "text": "Sí, a las 10 nos va bien"})   # edited before sending
    r = msg.apply_action("send_draft", {})
    assert r["ok"] and r["text"] == "Sí, a las 10 nos va bien" and r["to"] == "ana@x.com"
    d = msg.load_db()
    assert d["pending_reply"][0]["text"] == "Sí, a las 10 nos va bien"
    assert d["draft"] is None
    assert d["items"] == [], "responder marca leído y quita el pendiente, como reply"


def test_send_draft_with_nothing_dictated_says_so(sandbox):
    _seed([_EMAIL])
    r = msg.apply_action("send_draft", {})
    assert r["ok"] is False and r["error"] == "no_draft"


def test_an_empty_draft_clears_it_instead_of_storing_blank_text(sandbox):
    _seed([_EMAIL])
    msg.apply_action("draft", {"n": 1, "text": "algo"})
    r = msg.apply_action("draft", {"n": 1, "text": "   "})
    assert r["ok"] and r.get("cleared") is True
    assert msg.view_data()["draft"] is None


def test_a_draft_with_no_resolvable_target_is_refused(sandbox):
    _seed([])
    r = msg.apply_action("draft", {"n": 99, "text": "hola"})
    assert r["ok"] is False and r["error"] == "no_target"


def test_send_draft_re_resolves_against_the_live_item_not_a_stale_copy(sandbox):
    """If the item is dismissed elsewhere between drafting and sending, `send_draft` must not blindly reuse
    the identity captured at draft time — it re-resolves, exactly like the fallback `reply` already trusts."""
    _seed([_EMAIL])
    msg.apply_action("draft", {"n": 1, "text": "Confirmado"})
    msg.apply_action("dismiss", {"n": 1})                          # item leaves `items` before sending
    r = msg.apply_action("send_draft", {})
    # No live item left: falls back to the STORED target identity (still enough to address a real send to).
    assert r["ok"] and r["to"] == "ana@x.com"


def test_composing_a_thread_reply_needs_no_n_and_targets_the_open_chat(sandbox):
    _seed([_WA])
    db = msg.load_db()
    db["active_chat"] = {"platform": "whatsapp", "chatId": "34600"}
    store.save(msg.WIDGET_ID, db)
    r = msg.apply_action("draft", {"text": "Perfecto, nos vemos"})
    assert r["ok"]
    r2 = msg.apply_action("send_draft", {})
    assert r2["ok"] and r2["to"] == "34600"


def test_the_manifest_declares_every_new_action(sandbox):
    """V2-540: an undeclared capability is one the model NARRATES rather than uses."""
    import json
    import pathlib
    man = json.loads((pathlib.Path(msg.__file__).parent / "manifest.json").read_text(encoding="utf-8"))
    for name in ("draft", "send_draft", "set_signature", "set_signature_line", "clear_signature"):
        assert name in man["actions"], f"{name} no está declarada"


# ── signature ────────────────────────────────────────────────────────────────────────────────────────────

def test_set_signature_line_builds_up_without_wiping_the_others(sandbox, monkeypatch):
    from config import connectors as conn_store
    monkeypatch.setattr(conn_store, "_read", lambda: {})
    written = {}
    monkeypatch.setattr(conn_store, "_write", lambda d: written.update(d))
    msg.apply_action("set_signature_line", {"line": 1, "text": "Ricardo"})
    conn_store._read = lambda: written
    r = msg.apply_action("set_signature_line", {"line": 3, "text": "ricardo@x.com"})
    assert r["ok"] and r["lines"] == ["Ricardo", "", "ricardo@x.com"]


def test_setting_a_sparse_line_then_filling_the_gap_does_not_clobber_the_line_after_it(sandbox, monkeypatch):
    """Caught live, verifying this exact feature (2026-09-07): dictate line 1, then line 3 — the middle line
    stays an empty PLACEHOLDER, `['Ricardo', '', 'ricardo@x.com']`. Filling line 2 afterward must land in
    that middle slot, not overwrite line 3 — which is exactly what happened when the read-modify-write used
    `connectors.email.config.signature_lines()`, whose OWN reader filters blank lines for the sender (right
    there, wrong here): it silently collapsed the sparse array to two elements before the next line index
    was computed against it."""
    from config import connectors as conn_store
    store_data = {}
    monkeypatch.setattr(conn_store, "_read", lambda: store_data)
    monkeypatch.setattr(conn_store, "_write", lambda d: store_data.update(d))
    msg.apply_action("set_signature_line", {"line": 1, "text": "Ricardo"})
    msg.apply_action("set_signature_line", {"line": 3, "text": "ricardo@x.com"})
    assert store_data["email"]["signature_lines"] == ["Ricardo", "", "ricardo@x.com"]
    r = msg.apply_action("set_signature_line", {"line": 2, "text": "Director"})
    assert r["ok"] and r["lines"] == ["Ricardo", "Director", "ricardo@x.com"]


def test_set_signature_replaces_the_whole_thing(sandbox, monkeypatch):
    from config import connectors as conn_store
    monkeypatch.setattr(conn_store, "_read", lambda: {})
    written = {}
    monkeypatch.setattr(conn_store, "_write", lambda d: written.update(d))
    r = msg.apply_action("set_signature", {"lines": ["Ana", "Directora"]})
    assert r["ok"] and r["lines"] == ["Ana", "Directora"]
    assert written["email"]["signature_lines"] == ["Ana", "Directora"]


def test_clear_signature_empties_it(sandbox, monkeypatch):
    from config import connectors as conn_store
    monkeypatch.setattr(conn_store, "_read", lambda: {"email": {"signature_lines": ["Ana"]}})
    written = {}
    monkeypatch.setattr(conn_store, "_write", lambda d: written.update(d))
    r = msg.apply_action("clear_signature", {})
    assert r["ok"] and r["lines"] == []
    assert written["email"]["signature_lines"] == []


def test_view_data_publishes_the_signature(sandbox, monkeypatch):
    from connectors.email import config as email_cfg
    monkeypatch.setattr(email_cfg, "signature_lines", lambda: ["Ricardo", "CEO"])
    _seed([])
    assert msg.view_data()["email_signature"] == ["Ricardo", "CEO"]


def test_mensajeria_is_deliberately_exempt_from_the_stdlib_only_gate():
    """data.py:apply_action now reaches `config/connectors.py` for the signature — the SAME store the
    connect wizard already writes account credentials to, read lazily inside a function body exactly like
    `youtube`'s own `_svc()`. `make test-widgets` enforces stdlib-only for every widget NOT in this set; this
    pins the exemption is the deliberate one this file added, not an accidental relaxation of the gate."""
    from widgets import validator
    assert "mensajeria" in validator._STDLIB_EXEMPT
