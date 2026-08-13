import httpx
import pytest

from nucleo import account_routing


CP = "https://zaelar-control-plane.example.workers.dev"


@pytest.fixture(autouse=True)
def _clean_cache():
    account_routing._reset_cache_for_tests()
    yield
    account_routing._reset_cache_for_tests()


def _fake_client(monkeypatch, *, payload=None, status=200, raises=None, calls=None):
    """Stands in for httpx.AsyncClient. Records the headers each call went out with, because "did we
    present our credential?" is one of the things under test."""

    class _FakeResponse:
        status_code = status

        def json(self):
            return payload or {}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, headers=None):
            if calls is not None:
                calls.append({"url": url, "headers": headers or {}})
            if raises is not None:
                raise raises
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _FakeClient())


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


# --- the three-way answer -----------------------------------------------------------------------


@pytest.mark.anyio
async def test_resolved_carries_the_owning_machine(monkeypatch):
    _fake_client(monkeypatch, payload={"loggedIn": True, "machine": {"fly_machine_id": "m_target"}})
    assert await account_routing.resolve_session_machine("tok_abc", control_plane_url=CP) == (
        account_routing.RESOLVED,
        "m_target",
    )


@pytest.mark.anyio
async def test_a_token_the_resolver_rejects_is_no_session_not_unavailable(monkeypatch):
    _fake_client(monkeypatch, payload={"loggedIn": False})
    assert await account_routing.resolve_session_machine("tok_expired", control_plane_url=CP) == (
        account_routing.NO_SESSION,
        None,
    )


@pytest.mark.anyio
async def test_a_live_session_with_no_machine_on_record_is_not_ours_to_serve(monkeypatch):
    _fake_client(monkeypatch, payload={"loggedIn": True, "machine": {}})
    assert await account_routing.resolve_session_machine("tok_new", control_plane_url=CP) == (
        account_routing.NO_SESSION,
        None,
    )


@pytest.mark.anyio
async def test_a_network_failure_is_unavailable_and_never_raises(monkeypatch):
    """The old contract collapsed this into the same `None` as "not a session", and the caller read
    that as permission to serve. Keeping the two apart is the whole point."""
    _fake_client(monkeypatch, raises=RuntimeError("network down"))
    assert await account_routing.resolve_session_machine("tok_x", control_plane_url=CP) == (
        account_routing.UNAVAILABLE,
        None,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("status", [401, 403, 500, 503])
async def test_a_rejected_or_broken_lookup_is_unavailable_not_a_verdict(monkeypatch, status):
    """401 means WE could not ask, not that the visitor is a stranger. Reporting it as NO_SESSION
    would turn one credential mistake into a silent mass logout."""
    _fake_client(monkeypatch, status=status, payload={"error": "unauthorized"})
    assert await account_routing.resolve_session_machine("tok_y", control_plane_url=CP) == (
        account_routing.UNAVAILABLE,
        None,
    )


@pytest.mark.anyio
async def test_an_unconfigured_resolver_is_unavailable_without_touching_the_network(monkeypatch):
    calls = []
    _fake_client(monkeypatch, payload={"loggedIn": True}, calls=calls)
    assert await account_routing.resolve_session_machine("tok_z", control_plane_url="") == (
        account_routing.UNAVAILABLE,
        None,
    )
    assert calls == []


# --- the credential -----------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_lookup_presents_the_configured_credential(monkeypatch):
    """The routing lookup used to go out bare while every other caller of that endpoint was
    authenticated — so closing the endpoint would have silently broken routing."""
    monkeypatch.setenv("CONTROL_PLANE_SERVICE_TOKEN", "tok-service")
    calls = []
    _fake_client(monkeypatch, payload={"loggedIn": True, "machine": {"fly_machine_id": "m"}}, calls=calls)
    await account_routing.resolve_session_machine("tok_h", control_plane_url=CP)
    assert calls[0]["headers"].get("X-Service-Token") == "tok-service"


@pytest.mark.anyio
async def test_no_credential_configured_sends_no_header_at_all(monkeypatch):
    monkeypatch.delenv("CONTROL_PLANE_SERVICE_TOKEN", raising=False)
    calls = []
    _fake_client(monkeypatch, payload={"loggedIn": True, "machine": {"fly_machine_id": "m"}}, calls=calls)
    await account_routing.resolve_session_machine("tok_i", control_plane_url=CP)
    assert "X-Service-Token" not in calls[0]["headers"]


# --- caching ------------------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_resolved_answer_is_cached(monkeypatch):
    calls = []
    _fake_client(monkeypatch, payload={"loggedIn": True, "machine": {"fly_machine_id": "m_cached"}}, calls=calls)
    r1 = await account_routing.resolve_session_machine("tok_cache", control_plane_url=CP)
    r2 = await account_routing.resolve_session_machine("tok_cache", control_plane_url=CP)
    assert r1 == r2 == (account_routing.RESOLVED, "m_cached")
    assert len(calls) == 1


@pytest.mark.anyio
async def test_an_unavailable_answer_is_never_cached(monkeypatch):
    """Caching "I could not ask" would stretch a one-second blip into minutes of refusals."""
    calls = []
    _fake_client(monkeypatch, raises=RuntimeError("blip"), calls=calls)
    await account_routing.resolve_session_machine("tok_blip", control_plane_url=CP)
    await account_routing.resolve_session_machine("tok_blip", control_plane_url=CP)
    assert len(calls) == 2


@pytest.mark.anyio
async def test_a_negative_answer_is_cached_but_briefly(monkeypatch):
    """Without a negative cache, an unrecognised cookie buys a round-trip per request and this
    process becomes an amplifier against the resolver. It stays SHORT because "not a session"
    becomes "a session" as soon as the visitor logs in with the same cookie jar."""
    assert account_routing._NEGATIVE_CACHE_TTL < account_routing._CACHE_TTL
    calls = []
    _fake_client(monkeypatch, payload={"loggedIn": False}, calls=calls)
    await account_routing.resolve_session_machine("tok_neg", control_plane_url=CP)
    await account_routing.resolve_session_machine("tok_neg", control_plane_url=CP)
    assert len(calls) == 1


@pytest.fixture
def anyio_backend():
    return "asyncio"
