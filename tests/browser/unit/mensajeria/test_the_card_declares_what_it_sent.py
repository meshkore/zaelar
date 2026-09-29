"""V2-776 L2 · The messaging card declares what it SENT as a collection a verifier can read (node 4.231).

«Send Ethan a telegram with the new time» ends in a message that left. The card recorded it (`threads[*].msgs`
with `dir == "out"`) and nothing could read it back as a fact: `threads` is a dict, `rows` reads only declared
list collections, so `verify.py` could not attest «a Telegram to Ethan saying 4:30 went out» — the spec the
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
    db["threads"] = {"telegram|7477656357": {"name": "Ethan", "msgs": [
        {"id": "1", "dir": "out", "who": "Tú", "body": "Hey Ethan — catch-up tomorrow is now at 4:30 PM", "ts": time.time() - 30},
        {"id": "2", "dir": "in", "who": "Ethan", "body": "ok!", "ts": time.time() - 10}]}}
    db["pending_send"] = [{"ref": "s1", "platform": "email", "to": "ago@proars.com", "name": "Andrew",
                           "text": "Invoice attached — we're already trying Inworld", "at": time.time()}]
    data.store.save(data.WIDGET_ID, db)
    return data


def test_sent_is_a_flat_list_of_what_left_and_what_is_still_leaving(md):
    sent = md.view_data()["sent"]
    assert [r["name"] for r in sent] == ["Andrew", "Ethan"] or [r["name"] for r in sent] == ["Ethan", "Andrew"]
    ethan = next(r for r in sent if r["name"] == "Ethan")
    andrew = next(r for r in sent if r["name"] == "Andrew")
    assert ethan["platform"] == "telegram" and ethan["queued"] is False and "4:30" in ethan["body"]
    assert andrew["platform"] == "email" and andrew["queued"] is True
    assert not any(r.get("dir") == "in" for r in sent), "what came IN is the inbox, never «sent»"


def test_the_collection_is_declared_read_only_and_reads_from_the_view(md):
    from widgets import rows
    assert "sent" in rows.declared("mensajeria")
    assert rows.ops_for("mensajeria", "sent") == ("list",)
    assert len(rows.select("mensajeria", "sent", {"name~": "ethan", "body~": "4:30"})) == 1
    assert rows.select("mensajeria", "sent", {"name~": "Ethan", "queued": True}) == []


def test_the_send_to_postcondition_is_met_by_the_message_that_left(md):
    from nucleo import spec, verify
    dw = spec.render("mensajeria", "send_to", {"contact": "Ethan", "text": "catch-up tomorrow is now at 4:30 PM"})
    assert verify.check(dw) is True
    assert verify.check(spec.render("mensajeria", "send_to", {"contact": "Ethan", "text": "see you at 5"})) is False
