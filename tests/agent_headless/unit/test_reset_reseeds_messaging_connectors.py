"""`reset_all()` schedules a messaging-connector RESEED — but only when mensajería was actually blanked.

Blanking mensajería wipes the widget's `items` and its durable `taken` ledger (V2-607), but that is a
WIDGET-side operation: it never touches a connector's own process state (`connectors/email/service.py`'s
`_seen`/`_published`). Left alone, a message the connector already handed over once stays "already delivered"
forever from ITS point of view, even after Reset erases every trace of it from the widget — measured live: 1081
real unread in Gmail, zero reaching the widget after a Reset. `connectors/messaging/reseed.py::reseed_all()` is
the repair; this pins that `reset_all()` actually fires it, fire-and-forget, and ONLY when there was a
mensajería store to blank in the first place — a reset with no messaging widget ever opened must not go poking
at a mailbox for nothing.
"""
import asyncio

import pytest

from memory import db as memdb
from nucleo import reset
from widgets import store as _wstore


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _own_db_and_widget_store(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_DB", str(tmp_path / "zaelar.db"))
    # `blank_all()` reads `store.DATA_DIR` at CALL time (V2-567's lesson) — never the operator's real widgets.
    monkeypatch.setattr(_wstore, "DATA_DIR", str(tmp_path / "widgets_data"))
    memdb.reset_db()
    memdb.get_db()
    yield
    memdb.reset_db()


def _fake_reseed_all(calls):
    async def _run():
        calls.append(1)
        return {}
    return _run


@pytest.mark.anyio
async def test_reset_schedules_a_reseed_when_mensajeria_was_blanked(monkeypatch):
    _wstore.save("mensajeria", {"platforms": {"email": {"status": "connected"}}, "items": [{"n": 1}]})
    calls = []
    monkeypatch.setattr("connectors.messaging.reseed.reseed_all", _fake_reseed_all(calls))

    reset.reset_all()
    await asyncio.sleep(0)   # let the fire-and-forget task actually run

    assert calls == [1], "un reset que vació mensajería tiene que pedirle al conector que reseed-ee"


@pytest.mark.anyio
async def test_reset_does_not_schedule_a_reseed_with_no_messaging_state(monkeypatch):
    """No `widgets/_data/mensajeria/state.json` at all → nothing was blanked → nothing to reseed."""
    calls = []
    monkeypatch.setattr("connectors.messaging.reseed.reseed_all", _fake_reseed_all(calls))

    reset.reset_all()
    await asyncio.sleep(0)

    assert calls == [], "no debe tocar los conectores si mensajería nunca tuvo datos que vaciar"


@pytest.mark.anyio
async def test_a_failed_reseed_never_breaks_the_reset_itself(monkeypatch):
    _wstore.save("mensajeria", {"platforms": {}, "items": [{"n": 1}]})

    async def _boom():
        raise RuntimeError("mailbox on fire")

    monkeypatch.setattr("connectors.messaging.reseed.reseed_all", _boom)

    out = reset.reset_all()
    await asyncio.sleep(0)

    assert out["widgets"]["blanked"] == ["mensajeria"], "el reset en sí tiene que completarse igualmente"
