"""An echo of what the turn already did is not a failure (agenda-everyday-edits ES, 2026-10-15).

«Y quita el piano entero, toda la serie»: the model called two cancels; the first was refused and its repair
cancelled the piano series, and the model's own «whole series» call then found nothing left — «Voy con las dos
cosas. No he podido: No he entendido cuál quitar…» over a series that was gone. A refused op naming the row another
op of the SAME turn acted on (same card, same action) is that op's echo; an op that names another row, or none,
is still said.
"""
import asyncio

import pytest

from nucleo.flash import widget_data_turn as WDT


@pytest.fixture
def agenda(monkeypatch):
    from nucleo.flash import data_ops, frontend
    from widgets import actions as wa
    from widgets import server_api
    gone: set = set()

    async def brain_action(wid, act, pl):
        t = " ".join(str(pl.get("title") or "").lower().split())
        if t in gone or "ruiz" in t:
            return {"ok": False, "error": "not_found", "message": "No he entendido cuál quitar. ¿Cuál?"}
        gone.add(t)
        return {"ok": True}

    async def no_retry(*a, **k):
        return None

    async def nothing(*a, **k):
        return None
    monkeypatch.setattr(server_api, "brain_action", brain_action)
    monkeypatch.setattr(data_ops, "corrected_retry", no_retry)
    monkeypatch.setattr(data_ops, "_report_ignored", nothing)
    monkeypatch.setattr(data_ops, "admite_data_op", lambda a, adm, b: True)
    monkeypatch.setattr(data_ops, "one_open_instance", lambda w: w)
    monkeypatch.setattr(frontend, "action_mode", lambda *a, **k: wa.FAST)
    return gone


def _calls(*titles):
    return [{"name": "widget_data", "args": {"widget_id": "agenda", "action": "cancel_meeting",
                                             "payload": {"title": t}}} for t in titles]


def test_the_second_cancel_of_the_same_series_is_not_said_as_a_failure(agenda):
    parte = asyncio.run(WDT.execute(_calls("Clase de piano de Abril", "Clase de piano de  abril")))
    assert parte["executed"] == "widget_data" and not parte.get("fallidas"), parte


def test_a_row_that_was_not_there_is_still_said(agenda):
    parte = asyncio.run(WDT.execute(_calls("Clase de piano de Abril", "Revisión con el doctor Ruiz")))
    assert [f["act"] for f in parte.get("fallidas") or []] == ["cancel_meeting"], parte
