import httpx
import pytest

from nucleo import demo_routing


def test_my_session_id_none_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_SESSION", raising=False)
    assert demo_routing.my_session_id() is None


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
