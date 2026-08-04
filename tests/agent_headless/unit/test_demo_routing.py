import httpx
import pytest

from nucleo import demo_routing


@pytest.fixture(autouse=True)
def _reset_pool_state(monkeypatch):
    """The warm-pool pin is a process-global — reset it (and the pool env) around every test so
    order can't leak a pinned session into an unrelated assertion."""
    monkeypatch.delenv("ZAELAR_DEMO_POOL", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_ROUTER", raising=False)
    demo_routing._PINNED_SESSION = None
    yield
    demo_routing._PINNED_SESSION = None


def test_my_session_id_none_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    assert demo_routing.my_session_id() is None


# ── warm pool: is_demo_machine + pin_session (2026-08-04) ───────────────────────────────────────────
def test_is_demo_machine_false_on_selfhost(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_POOL", raising=False)
    assert demo_routing.is_demo_machine() is False


def test_is_demo_machine_true_per_session(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
    assert demo_routing.is_demo_machine() is True


def test_is_demo_machine_true_for_unbound_pool(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_POOL", "1")
    assert demo_routing.is_demo_machine() is True
    assert demo_routing.my_session_id() is None  # a demo machine, but not yet bound to a session


def test_pool_pins_on_first_session(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_POOL", "1")
    demo_routing.pin_session("sess-1")
    assert demo_routing.my_session_id() == "sess-1"
    # first visitor wins — a stray later ?s= never re-binds a live machine
    demo_routing.pin_session("sess-2")
    assert demo_routing.my_session_id() == "sess-1"


def test_fixed_session_ignores_pin(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "fixed-env")
    demo_routing.pin_session("sneaky")  # a per-session machine's identity is immutable
    assert demo_routing.my_session_id() == "fixed-env"


def test_pool_off_string_is_not_demo(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_POOL", "0")
    assert demo_routing.is_demo_machine() is False


def test_router_is_demo_but_never_pins(monkeypatch):
    """The base router routes sessions but must NEVER bind one as its own."""
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_POOL", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_ROUTER", "1")
    assert demo_routing.is_demo_machine() is True
    demo_routing.pin_session("sess-X")
    assert demo_routing.my_session_id() is None  # router stays unbound → falls through to fly-replay


def test_my_session_id_set(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_SESSION", "abc-123")
    assert demo_routing.my_session_id() == "abc-123"


def test_requested_session_id_cookie_wins():
    assert demo_routing.requested_session_id("cookie-val", "query-val") == "cookie-val"


def test_requested_session_id_falls_back_to_query():
    assert demo_routing.requested_session_id(None, "query-val") == "query-val"
    assert demo_routing.requested_session_id("", "query-val") == "query-val"


def test_requested_session_id_none_when_neither():
    assert demo_routing.requested_session_id(None, None) is None
    assert demo_routing.requested_session_id("", "") is None


@pytest.mark.anyio
async def test_find_machine_for_session_match(monkeypatch):
    machines = [
        {"id": "machine-A", "config": {"metadata": {"session_id": "other-session"}}},
        {"id": "machine-B", "config": {"metadata": {"session_id": "target-session"}}},
    ]

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return machines

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    result = await demo_routing.find_machine_for_session(
        "target-session", app_name="zaelar-demo", api_token="fake"
    )
    assert result == "machine-B"


@pytest.mark.anyio
async def test_find_machine_for_session_no_match(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [{"id": "machine-A", "config": {"metadata": {"session_id": "unrelated"}}}]

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    result = await demo_routing.find_machine_for_session(
        "missing-session", app_name="zaelar-demo", api_token="fake"
    )
    assert result is None


@pytest.mark.anyio
async def test_find_machine_for_session_fails_open_on_error(monkeypatch):
    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, headers=None):
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    result = await demo_routing.find_machine_for_session(
        "any-session", app_name="zaelar-demo", api_token="fake"
    )
    assert result is None  # never raises — fail-open


@pytest.fixture
def anyio_backend():
    return "asyncio"
