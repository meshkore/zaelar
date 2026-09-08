"""Reset wipes the widget's memory of what it delivered — this connector's OWN memory has to catch up, too.

The operator, live: Gmail connected, 1081 real unread messages, zero reaching the widget after a Reset. Not a
disconnection — `config/connectors.json` and `widgets/_data/mensajeria/state.json` both said `connected`. The
cause: `_seen`/`_published` (module-level, populated once at connect by `seed_from_mailbox` and again on every
real delivery) are cleared ONLY by `stop()` (a full disconnect) — Reset (`widgets/reset.py` ->
`widgets/mensajeria/data.py::blank()`) wipes the widget's `items` and its durable `taken` ledger, but never
touches this connector's process state. So a message this connector already handed over once stayed marked
"already delivered" forever from its own point of view, even with the widget's own record of it gone.

`reseed()` is the repair: release the same BACKFILL-sized recent-unread slice `seed_from_mailbox` already hands
over on a fresh connect, so the connector's next poll tick redelivers it — straight into the freshly-blanked
store.
"""
import pytest

from connectors.email import service


class _FakeTask:
    def done(self):
        return False


class _FakeMailbox:
    def __init__(self, read, unread, *, reachable=True):
        self._read, self._unread, self._reachable = set(read), list(unread), reachable

    def test_connection(self):
        return (True, "") if self._reachable else (False, "boom")

    def inbox_split(self):
        return set(self._read), list(self._unread)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def _clean():
    service._seen.clear()
    service._published.clear()
    service._set_unread_total(-1)
    service._task = None
    yield
    service._seen.clear()
    service._published.clear()
    service._set_unread_total(-1)
    service._task = None


def _mark_running():
    service._task = _FakeTask()


@pytest.mark.anyio
async def test_reseed_releases_only_the_recent_backfill_slice(monkeypatch):
    """The exact shape of the incident: 50 unread, every one of them already `_seen` from a prior delivery."""
    _mark_running()
    unread = [f"u{i}" for i in range(50)]
    mb = _FakeMailbox(read=["r1"], unread=unread)
    monkeypatch.setattr(service.config, "mailbox", lambda: mb)
    service._seen.update(unread)
    service._seen.add("r1")
    service._published.update(unread)

    n = await service.reseed()

    assert n == 50
    recent = set(unread[-service.BACKFILL:])
    old = set(unread[:-service.BACKFILL])
    assert recent.isdisjoint(service._seen), "el backlog reciente sigue marcado como ya visto"
    assert recent.isdisjoint(service._published), "sigue marcado como ya publicado al bus"
    assert old <= service._seen, "liberó más de lo que el backfill permite — inundaría el widget"
    assert "r1" in service._seen, "el correo LEÍDO no debe volver a entrar"
    assert service.unread_total() == 50


@pytest.mark.anyio
async def test_a_small_unread_backlog_is_released_whole(monkeypatch):
    _mark_running()
    unread = ["u1", "u2", "u3"]
    monkeypatch.setattr(service.config, "mailbox", lambda: _FakeMailbox(read=[], unread=unread))
    service._seen.update(unread)
    service._published.update(unread)

    n = await service.reseed()

    assert n == 3
    assert set(unread).isdisjoint(service._seen)


@pytest.mark.anyio
async def test_reseed_does_nothing_when_the_connector_is_not_running(monkeypatch):
    """`_task` is None/done → the loop is not live, so touching the real mailbox would be wasted network."""
    called = []
    monkeypatch.setattr(service.config, "mailbox", lambda: called.append(1) or _FakeMailbox([], []))

    n = await service.reseed()

    assert n == -1
    assert not called, "no debería ni tocar el buzón si el conector no está vivo"


@pytest.mark.anyio
async def test_reseed_is_a_noop_when_the_mailbox_is_unreachable(monkeypatch):
    _mark_running()
    monkeypatch.setattr(service.config, "mailbox", lambda: _FakeMailbox([], ["u1"], reachable=False))
    service._seen.add("u1")

    n = await service.reseed()

    assert n == -1
    assert "u1" in service._seen, "un buzón inalcanzable no debe liberar nada"


@pytest.mark.anyio
async def test_reseed_is_a_noop_when_config_hands_back_no_mailbox(monkeypatch):
    """`config.mailbox()` returns None when credentials are missing — same fail-soft shape as `_loop`."""
    _mark_running()
    monkeypatch.setattr(service.config, "mailbox", lambda: None)

    n = await service.reseed()

    assert n == -1
