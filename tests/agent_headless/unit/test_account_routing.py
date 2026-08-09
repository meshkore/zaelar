import httpx
import pytest

from nucleo import account_routing


def test_my_machine_id_none_by_default(monkeypatch):
    monkeypatch.delenv("FLY_MACHINE_ID", raising=False)
    assert account_routing.my_machine_id() is None


def test_my_machine_id_reads_the_fly_runtime_var(monkeypatch):
    monkeypatch.setenv("FLY_MACHINE_ID", "080d69da092648")
    assert account_routing.my_machine_id() == "080d69da092648"


def test_is_account_routing_machine_false_on_selfhost_and_demo(monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.delenv("ZAELAR_ACCOUNT_ROUTER", raising=False)
    assert account_routing.is_account_routing_machine() is False


def test_is_account_routing_machine_true_for_a_real_account(monkeypatch):
    monkeypatch.setenv("ZAELAR_USER_ID", "did:key:z6MkExample")
    monkeypatch.delenv("ZAELAR_ACCOUNT_ROUTER", raising=False)
    assert account_routing.is_account_routing_machine() is True


def test_is_account_routing_machine_true_for_the_base_router(monkeypatch):
    """2026-08-09 fix: the base Machine has no ZAELAR_USER_ID of its own but MUST still attempt
    routing (found live: without this it silently served the wrong content for a mismatched cookie)."""
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    monkeypatch.setenv("ZAELAR_ACCOUNT_ROUTER", "1")
    assert account_routing.is_account_routing_machine() is True


@pytest.mark.anyio
async def test_find_machine_for_session_returns_the_verified_machine_id(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"loggedIn": True, "machine": {"fly_machine_id": "m_target"}}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    result = await account_routing.find_machine_for_session(
        "tok_abc", control_plane_url="https://zaelar-control-plane.example.workers.dev"
    )
    assert result == "m_target"


@pytest.mark.anyio
async def test_find_machine_for_session_none_when_not_logged_in(monkeypatch):
    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"loggedIn": False}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    result = await account_routing.find_machine_for_session(
        "tok_expired", control_plane_url="https://zaelar-control-plane.example.workers.dev"
    )
    assert result is None


@pytest.mark.anyio
async def test_find_machine_for_session_fails_open_on_error(monkeypatch):
    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            raise RuntimeError("network down")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    result = await account_routing.find_machine_for_session(
        "tok_x", control_plane_url="https://zaelar-control-plane.example.workers.dev"
    )
    assert result is None  # never raises — fail-open


@pytest.mark.anyio
async def test_find_machine_for_session_is_cached(monkeypatch):
    calls = []

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"loggedIn": True, "machine": {"fly_machine_id": "m_cached"}}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            calls.append(url)
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())

    r1 = await account_routing.find_machine_for_session("tok_cache", control_plane_url="https://cp.example.com")
    r2 = await account_routing.find_machine_for_session("tok_cache", control_plane_url="https://cp.example.com")
    assert r1 == r2 == "m_cached"
    assert len(calls) == 1  # second call served from cache, no second network call


@pytest.fixture
def anyio_backend():
    return "asyncio"
