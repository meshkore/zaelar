"""A hard RESET records WHO ordered it, not only what it destroyed (V2-567).

Measured 2026-09-03 on the operator's own engine (events `280189-280212`): a hard reset fired in the middle of
a live errand — killing one browser task, two escalations, one worker and seven turns of conversation — with
**no `ui/topbar:reset`, no `ui/orb:power` and no `run/stop` in front of it**. The button emits `topbar:reset`
when it is clicked, so the absence of that event is proof the button was not the author, and nothing anywhere
could say what was.

What it cost is not the reset. It is that fifteen seconds later the operator said «has cerrado el navegador y
el widget de resultados, me parece absurdo» and the engine answered «tienes razón, cerrarlos sin haber
terminado no tenía sentido» — apologising for an act it had not chosen, and handing the operator a false model
of his own system. The RESET event already carried a full inventory of the damage (`killed`, `blanked`,
`kept`, `discarded`); the one field missing was the author of it.

The attribution is deliberately coarse — client host and a bounded User-Agent — because its whole job is to
separate «the desktop frontend» from «something automated», which is the question actually asked afterwards.
"""
from __future__ import annotations

import inspect

import pytest

from server import voice_api


class _Req:
    """The shape FastAPI hands the endpoint: a client with a host, and case-insensitive headers."""

    def __init__(self, host: str = "127.0.0.1", ua: str = "", *, no_client: bool = False):
        self.client = None if no_client else type("C", (), {"host": host})()
        self.headers = {"user-agent": ua}


def test_the_author_travels_with_the_event():
    who = voice_api._who_asked(_Req("127.0.0.1", "Mozilla/5.0 … Chrome/152.0.0.0 Safari/537.36"))
    assert who["host"] == "127.0.0.1"
    assert "Chrome/152" in who["ua"]


def test_a_harness_is_distinguishable_from_a_browser():
    """The point of keeping the User-Agent: an automated caller sends a fixed, short string while a real
    browser's carries its version. Without this the two are the same anonymous POST."""
    browser = voice_api._who_asked(_Req(ua="Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/152.0.0.0 Safari/537.36"))
    harness = voice_api._who_asked(_Req(ua="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"))
    assert browser["ua"] != harness["ua"]


def test_a_long_user_agent_is_bounded():
    assert len(voice_api._who_asked(_Req(ua="x" * 400))["ua"]) == 120


@pytest.mark.parametrize("req", [None, _Req(no_client=True), _Req(ua="")])
def test_attribution_never_breaks_the_reset(req):
    """Fail-soft on purpose, and this is the sensitivity that makes it safe: a reset is how the operator gets
    out of a mess, so it must never fail because we could not name its author. Empty strings, not an exception."""
    who = voice_api._who_asked(req)
    assert set(who) == {"host", "ua"}
    assert all(isinstance(v, str) for v in who.values())


def test_both_hard_reset_doors_carry_it():
    """`/reset/hard` and `/api/reset/full` are TWO endpoints that both destroy live work — the same pair that
    `test_the_stage_is_cleared_before_every_case` keeps honest. Attributing only one leaves the other silent,
    and a rule each caller has to remember is not a rule."""
    for fn in (voice_api.reset_hard, voice_api.reset_full):
        src = inspect.getsource(fn)
        assert "_who_asked(request)" in src, f"{fn.__name__} destroys live work without recording who asked"
        assert "request" in inspect.signature(fn).parameters, f"{fn.__name__} cannot see its caller"
