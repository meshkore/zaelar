"""V2-776 L2 · The messaging card declares what it SENT as a collection a verifier can read (node 4.231).

«Send Rowan a telegram with the new time» ends in a message that left. The card recorded it (`threads[*].msgs`
with `dir == "out"`) and nothing could read it back as a fact: `threads` is a dict, `rows` reads only declared
list collections, so `verify.py` could not attest «a Telegram to Rowan saying 4:30 went out» — the spec the
`send_to` action declares. Now `view_data()["sent"]` is that flat list (queued orders included, marked), the
manifest declares it as a read-only collection FROM THE VIEW, and the action's postcondition is met by it.
"""
import time

import pytest


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data
    db = data.load_db()
    db["threads"] = {"telegram|7477656357": {"name": "Rowan", "msgs": [
        {"id": "1", "dir": "out", "who": "Tú", "body": "Hey Rowan — catch-up tomorrow is now at 4:30 PM", "ts": time.time() - 30},
        {"id": "2", "dir": "in", "who": "Rowan", "body": "ok!", "ts": time.time() - 10}]}}
    db["pending_send"] = [{"ref": "s1", "platform": "email", "to": "contact@example.com", "name": "Quinn",
                           "text": "Invoice attached — we're already trying Inworld", "at": time.time()}]
    data.store.save(data.WIDGET_ID, db)
    return data


def test_sent_is_a_flat_list_of_what_left_and_what_is_still_leaving(md):
    sent = md.view_data()["sent"]
    assert [r["name"] for r in sent] == ["Quinn", "Rowan"] or [r["name"] for r in sent] == ["Rowan", "Quinn"]
    rowan = next(r for r in sent if r["name"] == "Rowan")
    quinn = next(r for r in sent if r["name"] == "Quinn")
    assert rowan["platform"] == "telegram" and rowan["queued"] is False and "4:30" in rowan["body"]
    assert quinn["platform"] == "email" and quinn["queued"] is True
    assert not any(r.get("dir") == "in" for r in sent), "what came IN is the inbox, never «sent»"


def test_the_collection_is_declared_read_only_and_reads_from_the_view(md):
    from widgets import rows
    assert "sent" in rows.declared("mensajeria")
    assert rows.ops_for("mensajeria", "sent") == ("list",)
    assert len(rows.select("mensajeria", "sent", {"name~": "rowan", "body~": "4:30"})) == 1
    assert rows.select("mensajeria", "sent", {"name~": "Rowan", "queued": True}) == []


def test_the_send_to_postcondition_is_met_by_the_message_that_left(md):
    from nucleo import spec, verify
    dw = spec.render("mensajeria", "send_to", {"contact": "Rowan", "text": "catch-up tomorrow is now at 4:30 PM"})
    assert verify.check(dw) is True
    # Demo pass 68, C5: the clause carried the model's whole draft (`body~`) and the message that left was worded by
    # the card, so a Telegram Rowan received read «unmet». What is attestable is that it went out to HIM.
    assert verify.check(spec.render("mensajeria", "send_to", {"contact": "Rowan", "text": "see you at 5"})) is True
    assert verify.check(spec.render("mensajeria", "send_to", {"contact": "Anna", "text": "see you at 5"})) is False
