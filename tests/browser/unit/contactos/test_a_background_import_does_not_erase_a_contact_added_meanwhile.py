"""A background import and a concurrent add must not erase each other (demo pass 2026-09-28).

After a reset the Telegram import loaded the (empty) directory, spent seconds merging 2,692 rows and saved —
erasing «Rowan», added in between; his Telegram message then failed «no tengo a Rowan en el directorio».
One widget action = one read-modify-write (`store.mutating`), for the dispatcher and the background writers.
"""
import threading
import time

import pytest


@pytest.fixture
def ct(tmp_path, monkeypatch):
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    from widgets.contactos import data as d
    return d


def test_the_slow_import_and_the_add_both_survive(ct, monkeypatch):
    from widgets.contactos import imports, sources
    from widgets import server_api
    real = imports.absorb

    def slow_absorb(db, got, source=""):
        time.sleep(0.4)                                  # the merge of 2,692 rows, shortened
        return real(db, got, source=source)
    monkeypatch.setattr(imports, "absorb", slow_absorb)
    got = {"ok": True, "contacts": [{"name": "Laura Import", "phones": ["+34600000001"]}]}
    t = threading.Thread(target=lambda: sources._absorb("telegram", got))
    t.start()
    time.sleep(0.1)                                      # the import has loaded; now he adds Rowan
    server_api._call_widget("contactos", "apply_action",
                            lambda fn: fn("add_contact", {"name": "Rowan", "channels": [
                                {"platform": "telegram", "handle": "@x", "chatId": "1"}]}))
    t.join()
    names = {c["name"] for c in ct.load_db()["contacts"]}
    assert "Rowan" in names, names


def test_the_lock_is_one_per_widget_and_reentrant():
    from widgets import store
    a, b = store.mutating("contactos"), store.mutating("contactos")
    assert a is b and store.mutating("results::x") is store.mutating("results")
    with a:
        with b:
            pass
