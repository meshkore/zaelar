"""Node 7.11 — REQUEST ADMISSION (server/ingress.py).

These cases exist because of a REAL bug, not to complete a matrix: until 2026-08-13, the routing
middleware called `call_next()` in all FOUR rejection branches, so an anonymous request to the shared
hostname received a tenant's data. Each test below locks one of those four branches closed, and the
last two lock down what CANNOT be closed (the shell, the assets, the liveness probe) — because closing
the probe leaves the process without traffic, and "secure but turned off" is not the objective.

`decide` is pure: no server, no network, and no clock.
"""
import pytest

from nucleo import account_routing as ar
from server import ingress


MINE = "d8d0793f04d5e8"
OTHER = "080d69da092648"


def _decide(**over):
    base = dict(
        path="/api/memory/map",
        has_cookie=True,
        resolver_configured=True,
        outcome=ar.RESOLVED,
        target=MINE,
        mine=MINE,
    )
    base.update(over)
    return ingress.decide(**base)


# --- what is served -----------------------------------------------------------------------------


def test_a_session_that_resolves_here_is_served():
    assert _decide() == (ingress.SERVE, "session_owned_here")


@pytest.mark.parametrize("path", ["/", "/healthz", "/favicon.ico", "/static/app/main.js"])
def test_the_shell_assets_and_the_liveness_probe_answer_without_a_session(path):
    """The shell and assets are identical in every process and belong to no one; `/healthz` must
    respond or the supervisor stops sending traffic to a perfectly healthy process."""
    assert _decide(path=path, has_cookie=False, outcome=None, target=None) == (
        ingress.SERVE,
        "public_path",
    )


def test_the_allowlist_is_not_fooled_by_a_prefix_that_merely_starts_the_same():
    """`/staticky` is not `/static/`: the prefix is checked with the slash included."""
    assert ingress.is_public_path("/static/x.js") is True
    assert ingress.is_public_path("/staticky") is False
    assert ingress.is_public_path("/healthz/../api/memory/map") is False


# --- the four branches that previously served --------------------------------------------------


def test_no_cookie_is_refused_instead_of_served_locally():
    assert _decide(has_cookie=False, outcome=None, target=None) == (ingress.DENY, "no_session")


def test_an_unverifiable_session_is_refused_a_timeout_is_not_permission():
    assert _decide(outcome=ar.UNAVAILABLE, target=None) == (
        ingress.UNAVAILABLE,
        "session_unverifiable",
    )


def test_a_session_the_resolver_does_not_recognise_is_refused():
    assert _decide(outcome=ar.NO_SESSION, target=None) == (
        ingress.DENY,
        "session_not_recognized",
    )


def test_a_process_that_cannot_ask_serves_nothing():
    """A missing environment variable used to be the system's MOST permissive configuration. Not anymore."""
    assert _decide(resolver_configured=False) == (ingress.UNAVAILABLE, "resolver_not_configured")
    assert _decide(mine=None) == (ingress.UNAVAILABLE, "resolver_not_configured")


# --- distribution among processes ---------------------------------------------------------------


def test_a_session_owned_elsewhere_is_handed_over_not_answered_here():
    assert _decide(target=OTHER) == (ingress.REPLAY, "session_owned_elsewhere")


def test_resolved_without_a_target_is_closed_not_guessed():
    assert _decide(target=None) == (ingress.UNAVAILABLE, "session_unverifiable")


# --- what the reasons MUST NOT carry ------------------------------------------------------------


def test_reasons_are_stable_slugs_and_never_echo_the_request():
    """The reason travels to the client and the log: including a token, path, or internal URL would be
    a leak in the most copied place in the system."""
    secret_ish = "/api/vault/reveal?token=abc123"
    for kw in (
        dict(has_cookie=False, outcome=None, target=None),
        dict(outcome=ar.UNAVAILABLE, target=None),
        dict(outcome=ar.NO_SESSION, target=None),
        dict(resolver_configured=False),
    ):
        _, reason = _decide(path=secret_ish, **kw)
        assert reason.replace("_", "").isalpha(), reason
        assert "abc123" not in reason and "/" not in reason
