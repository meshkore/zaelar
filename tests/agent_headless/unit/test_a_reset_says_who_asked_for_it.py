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


# ── the OTHER half of V2-567: a reset in a test must never reach the operator's real desk ─────────────────
def test_no_test_calls_reset_all_without_sandboxing_the_widget_store():
    """`reset_all()` blanks widgets by WALKING `store.DATA_DIR`, and that path is computed AT IMPORT TIME from
    `workspace.root()` — so `ZAELAR_WORKSPACE` set inside a fixture arrives too late to move it. A test that
    calls the real `reset_all()` without pointing `DATA_DIR` at a sandbox empties the operator's own cards.

    It is not hypothetical. Measured 2026-09-03: two runs of the DETERMINISTIC suite blanked the operator's
    live widgets in the middle of a real errand — the server log names his own sheet, `results--7ff4fd-1` —
    while he was watching. He reported his browser and results cards closing by themselves, and the engine,
    with no fact anywhere saying a reset had happened, agreed it had misbehaved and apologised.

    `test_rehydrate.py` had the sandbox and the right words for it since before that day («it is autouse and
    NOT optional: the protection cannot depend on the next test remembering to request it») — and the
    neighbour that also calls `reset_all()` did not have it. That is the whole lesson: **a rule each caller
    has to remember is not a rule**, so it is checked here instead of trusted."""
    import re
    from pathlib import Path as _P

    root = _P(__file__).resolve().parents[3] / "tests"
    offenders = []
    for py in sorted(root.rglob("test_*.py")):
        src = py.read_text(encoding="utf-8", errors="replace")
        # The CALL, not the mention: docstrings across the suite discuss `reset_all` on purpose.
        code = "\n".join(l for l in src.splitlines() if not l.lstrip().startswith("#"))
        if not re.search(r"\breset\.reset_all\(\)|\bnreset\.reset_all\(\)", code):
            continue
        if "DATA_DIR" not in code:
            offenders.append(str(py.relative_to(root.parent)))
    assert not offenders, (
        "these tests run the REAL reset_all() without sandboxing store.DATA_DIR, so they blank the operator's "
        f"live widgets: {offenders}. Point `widgets.store.DATA_DIR` at tmp_path in an autouse fixture.")
