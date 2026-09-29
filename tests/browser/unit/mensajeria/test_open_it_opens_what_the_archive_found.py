"""«Open it» after an archive search opens the mail it FOUND (node 4.237).

Demo pass 62, E2 (2026-09-29): «did inworld send me something?» found the receipt in the archive. Its
conversation was on the card — a thread brought back by an earlier «load previous», with no name — but not in the
inbox list, whose only row was an OVHcloud mail. «Open it» came back as «there's nothing to open», and the repair
pass then opened the ONE chat the list showed: the wrong mail. The card now remembers what the archive last found,
a bare `open` opens that, and its digest says so to the model.
"""
import time

import pytest

INWORLD = "invoice+statements@inworld.ai"
ROW = {"id": "3335", "platform": "email", "chat_id": INWORLD, "chat_name": "", "sender": "Inworld AI",
       "direction": "in", "ts": time.time() - 3600, "body": "[Asunto: Your receipt from Inworld AI #2281-4878]\nInworld AI",
       "msg_id": "220440"}


@pytest.fixture
def md(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.mensajeria import data, views
    monkeypatch.setattr(views, "archive_rows", lambda payload: [ROW] if "inworld" in str(payload).lower() else [])
    db = data.load_db()
    db["items"] = [{"n": 1, "platform": "email", "chatId": "support@services.ovhcloud.com", "name": "Soporte de OVHcloud",
                    "text": "[Asunto: Reinicio de hardware]", "ts": time.time() - 60, "messageId": "m-ovh"}]
    db["threads"] = {"email|support@services.ovhcloud.com": {"name": "Soporte de OVHcloud", "msgs": [
                         {"id": "m-ovh", "dir": "in", "who": "Soporte de OVHcloud", "body": "Reinicio", "ts": time.time() - 60}]},
                     f"email|{INWORLD}": {"name": "", "msgs": [
                         {"id": "220440", "dir": "in", "who": "", "body": "Your receipt", "ts": ROW["ts"]}]}}
    data.store.save(data.WIDGET_ID, db)
    return data


def test_a_bare_open_after_the_search_opens_the_found_mail_not_the_inbox_row(md):
    md.apply_action("search_archive", {"query": "inworld"})
    md.apply_action("open", {})
    assert md.load_db()["active_chat"] == {"platform": "email", "chatId": INWORLD}


def test_the_digest_tells_the_model_the_found_mail_is_on_the_card(md):
    md.apply_action("search_archive", {"query": "inworld"})
    from widgets.mensajeria import inbox_read
    digest = inbox_read.prompt_digest()
    assert "LO ÚLTIMO QUE ENCONTRASTE EN EL ARCHIVO" in digest and "Your receipt from Inworld AI #2281-4878" in digest
    assert "`open` sin nada" in digest


def test_a_named_open_still_wins_and_a_stale_find_opens_nothing(md, monkeypatch):
    md.apply_action("search_archive", {"query": "inworld"})
    md.apply_action("open", {"name": "OVHcloud"})
    assert md.load_db()["active_chat"]["chatId"] == "support@services.ovhcloud.com"
    db = md.load_db()
    db["active_chat"] = None
    db["last_found"]["at"] = time.time() - md.FOUND_TTL_S - 5
    md.store.save(md.WIDGET_ID, db)
    md.apply_action("open", {})
    assert not md.load_db().get("active_chat")
    assert md.last_found(md.load_db()) is None


def test_a_search_that_found_nothing_remembers_nothing(md):
    md.apply_action("search_archive", {"query": "nobody"})
    assert md.last_found(md.load_db()) is None
