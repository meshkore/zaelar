"""A contacts import never starts on its own — it waits for the operator to ask (2026-10-04).

The operator: «todo el proceso de importación de contactos, mensajes, mails, etc. debe ser natural, o debe
pedirse, pero no debemos forzar nada en background por nuestra cuenta… una persona de cero tiene que llegar a lo
mismo». Measured the same day: after a memory reset the directory was empty, Google's sync switch read as ON by
default, and the background tick pulled ~2 700 contacts on its own — holding the directory's lock for minutes,
so the demo's own first contact could not even be written. Telegram and WhatsApp already started OFF; Google now
does too, and stays on once he turns it on (V2-701's «permanent» holds after the yes).
"""
from __future__ import annotations


def test_a_fresh_directory_reads_the_google_sync_as_off():
    from widgets.contactos import gcontacts
    assert gcontacts.sync_state({})["auto"] is False


def test_the_tick_does_not_import_until_he_turns_it_on(monkeypatch):
    from widgets.contactos import gcontacts, data as d

    class _O:
        def tokens_present(self, _p): return True
    calls = []
    monkeypatch.setattr(gcontacts, "_oauth", lambda: _O())
    monkeypatch.setattr(gcontacts, "svc", lambda: object())
    monkeypatch.setattr(gcontacts, "sync", lambda db, **kw: calls.append(1) or {"ok": True})
    db = {"contacts": [], "sync": {}}
    monkeypatch.setattr(d, "load_db", lambda: db)

    class _Ctx:
        def save(self, _db): ...
    gcontacts.tick(_Ctx())
    assert calls == [], "a sync nobody asked for ran"
    db["sync"]["auto"] = True
    gcontacts.tick(_Ctx())
    assert calls == [1], "once he turned it on, the permanent sync runs"
