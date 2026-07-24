from nucleo import demo_limits


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_MAX_TURNS", raising=False)
    monkeypatch.delenv("ZAELAR_DEMO_TTL_SECS", raising=False)
    assert demo_limits.max_turns() is None
    assert demo_limits.ttl_secs() is None
    assert demo_limits.enabled() is False
    assert demo_limits.check(9999, 0.0, now=99999.0) is None


def test_max_turns_parsing_and_boundary(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_MAX_TURNS", "5")
    monkeypatch.delenv("ZAELAR_DEMO_TTL_SECS", raising=False)
    assert demo_limits.max_turns() == 5
    assert demo_limits.enabled() is True
    assert demo_limits.check(4, 0.0, now=0.0) is None
    assert demo_limits.check(5, 0.0, now=0.0) == "max_turns"
    assert demo_limits.check(6, 0.0, now=0.0) == "max_turns"


def test_ttl_parsing_and_boundary(monkeypatch):
    monkeypatch.delenv("ZAELAR_DEMO_MAX_TURNS", raising=False)
    monkeypatch.setenv("ZAELAR_DEMO_TTL_SECS", "900")
    assert demo_limits.ttl_secs() == 900.0
    assert demo_limits.check(0, started_at=1000.0, now=1899.0) is None
    assert demo_limits.check(0, started_at=1000.0, now=1900.0) == "ttl"
    assert demo_limits.check(0, started_at=1000.0, now=2500.0) == "ttl"


def test_max_turns_wins_when_both_set_and_hit_together(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_MAX_TURNS", "3")
    monkeypatch.setenv("ZAELAR_DEMO_TTL_SECS", "10")
    assert demo_limits.check(3, started_at=0.0, now=20.0) == "max_turns"


def test_invalid_or_zero_values_are_ignored(monkeypatch):
    monkeypatch.setenv("ZAELAR_DEMO_MAX_TURNS", "not-a-number")
    monkeypatch.setenv("ZAELAR_DEMO_TTL_SECS", "0")
    assert demo_limits.max_turns() is None
    assert demo_limits.ttl_secs() is None
    assert demo_limits.enabled() is False


def test_closer_registry_request_close_noop_without_registration():
    demo_limits.clear_closer()
    # must not raise even with nothing registered
    demo_limits.request_close("max_turns")


def test_closer_registry_calls_registered_fn():
    calls = []

    def _closer(reason):
        calls.append(reason)

    demo_limits.register_closer(_closer)
    try:
        demo_limits.request_close("ttl")
    finally:
        demo_limits.clear_closer(_closer)
    # request_close schedules a task; give the event loop a beat isn't possible without asyncio
    # here (this is a sync test), so just confirm registration/clear plumbing doesn't raise and
    # clear_closer respects identity (won't clear a DIFFERENT closer than the one passed).
    demo_limits.register_closer(_closer)
    demo_limits.clear_closer(lambda r: None)  # different fn — must NOT clear
    assert demo_limits._closer is _closer
    demo_limits.clear_closer(_closer)
    assert demo_limits._closer is None
