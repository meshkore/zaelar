"""V2-680 — a stored conversation keeps what reading a MAIL needs: subject, sender address, recipients.

The operator, reading an email inside the widget: «quiero ver el asunto, quiero ver quién lo envía, quiero
ver quién está en copia». None of the three survived into a thread message — `_norm` kept who/body/ts/read
and dropped the rest, so the reading pane had nothing to show even though the connector had already parsed
all of it. Fixing the pane without fixing this would have produced a screen that renders correctly and is
permanently blank in the two fields he asked for by name.

They are OPTIONAL on purpose: a WhatsApp message has no subject and no Cc, and storing an empty one would
put a label on the screen that states something false about the original.
"""
from __future__ import annotations

from widgets.mensajeria import thread


def _mail(**extra):
    m = {"messageId": "uid-1", "from": "Ana", "body": "[Asunto: Reunión]\n\nHola", "timestamp": 1700000000,
         "subject": "Reunión de mañana", "senderId": "ana@x.com",
         "recipients": ["marta@x.com", "pedro@x.com"]}
    m.update(extra)
    return m


def _stored(msg, direction="in"):
    """Read back through `window()` — the SAME door the widget's payload is built from, so this measures
    what actually reaches the screen rather than an internal shape the reader might not use."""
    db = {}
    assert thread.append(db, "email", "ana@x.com", msg, direction)
    return thread.window(db, "email", "ana@x.com")[-1]


def test_a_stored_mail_keeps_its_subject_sender_and_recipients():
    m = _stored(_mail())
    assert m["subject"] == "Reunión de mañana"
    assert m["senderId"] == "ana@x.com"
    assert m["recipients"] == ["marta@x.com", "pedro@x.com"]


def test_a_chat_message_stores_none_of_them():
    """The counterweight: a WhatsApp turn has no envelope, and inventing empty fields for it would put
    labels on screen that assert something about a message that never had them."""
    m = _stored({"messageId": "w1", "from": "Marta", "body": "¿Vienes?", "timestamp": 1700000000})
    assert "subject" not in m and "senderId" not in m and "recipients" not in m


def test_an_empty_recipient_list_is_not_stored():
    """A mail addressed only to us has no reply-all and no «Copia» row. Storing `[]` would be the same
    lie one step earlier."""
    m = _stored(_mail(recipients=[]))
    assert "recipients" not in m


def test_a_blank_address_in_the_list_is_dropped():
    m = _stored(_mail(recipients=["marta@x.com", "  ", ""]))
    assert m["recipients"] == ["marta@x.com"]


def test_a_mail_already_read_still_shows_its_envelope():
    """The payload the widget actually renders, built by `_thread_view`. Before this the envelope fields
    were merged only from a still-PENDING item, so they vanished the moment the mail was dealt with —
    exactly when the operator scrolls back to check who else was on it."""
    from widgets.mensajeria import views
    db = {}
    thread.append(db, "email", "ana@x.com", _mail(), "in")
    rows = views._thread_view(db, {"platform": "email", "chatId": "ana@x.com"}, [])   # NOTHING pending
    assert rows and rows[0]["subject"] == "Reunión de mañana"
    assert rows[0]["senderId"] == "ana@x.com"
    assert rows[0]["recipients"] == ["marta@x.com", "pedro@x.com"]
    assert rows[0]["from"] == "Ana"          # the thread's `who` reaches the widget as `from`


def test_everything_the_thread_already_kept_is_untouched():
    """The fields this file adds ride BESIDE the old ones — a thread message is read by the chat shapes
    too, and losing one of these would break WhatsApp and Telegram for a change about email."""
    m = _stored(_mail())
    assert m["id"] == "uid-1" and m["dir"] == "in" and m["who"] == "Ana"
    assert m["ts"] == 1700000000 and "Hola" in m["body"]
