from nucleo import account_limits


def test_should_close_only_on_a_confirmed_depleted_balance():
    assert account_limits.should_close(0) is True
    assert account_limits.should_close(-5) is True
    assert account_limits.should_close(0.01) is False
    assert account_limits.should_close(150) is False


def test_should_close_never_closes_on_unknown_balance():
    # None = the /usage report itself failed — never a reason to end the session.
    assert account_limits.should_close(None) is False


def test_closer_registry_request_close_noop_without_registration():
    account_limits.clear_closer()
    # must not raise even with nothing registered
    account_limits.request_close("balance_depleted")


def test_closer_registry_calls_registered_fn():
    calls = []

    def _closer(reason):
        calls.append(reason)

    account_limits.register_closer(_closer)
    try:
        account_limits.request_close("balance_depleted")
    finally:
        account_limits.clear_closer(_closer)
    account_limits.register_closer(_closer)
    account_limits.clear_closer(lambda r: None)  # different fn — must NOT clear
    assert account_limits._closer is _closer
    account_limits.clear_closer(_closer)
    assert account_limits._closer is None
