"""A test that stops the agent must stop it in ITS OWN database, never in the operator's.

Found the hard way (2026-08-31). A new test file drove `runstate.stop("test")` for real; `_persist` wrote the
switch to `sys_kv`; the root conftest resets only the in-process CACHE (it says so in its own docstring), so the
ROW stayed `stopped` — and the operator's very next engine restart obeyed it and came up with the agent off. It
does not fail loudly: the agent is simply off, with `src` naming whoever the test passed, so it does not even
look like a test did it. `tests/voice/unit/test_trace_cluster_session.py` had been doing exactly this with
`src="operator"` for two weeks.

The rule this ratchet holds: **a unit test never touches a live artefact.** Flipping the switch in RAM
(`runstate._state.update(...)`) needs nothing — that is what the root conftest does. But the moment a test calls
`stop()`/`start()`/`_persist()`, it is writing to a database, and that database has to be a temporary one
(`ZAELAR_DB`, the same fixture `tests/agent_headless/unit/test_runstate.py` has always used).
"""
import re
from pathlib import Path

TESTS = Path(__file__).resolve().parents[2]

#: The calls that reach `_persist` and therefore write `sys_kv`. `runstate.stopped()`/`state()` only READ, and a
#: direct `_state.update(...)` never leaves RAM — neither belongs here.
_PERSISTS = re.compile(r"runstate\.(stop|start|_persist)\s*\(")


def _persisting_test_files() -> list[Path]:
    out = []
    for p in sorted(TESTS.rglob("test_*.py")):
        body = p.read_text(encoding="utf-8", errors="ignore")
        # strip comments so a line ABOUT the rule cannot be mistaken for a call that breaks it
        code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
        if _PERSISTS.search(code):
            out.append(p)
    return out


def test_every_test_that_flips_the_switch_owns_its_database():
    offenders = []
    for p in _persisting_test_files():
        if "ZAELAR_DB" not in p.read_text(encoding="utf-8", errors="ignore"):
            offenders.append(str(p.relative_to(TESTS.parent)))
    assert not offenders, (
        "these tests persist the ⏻ switch into whatever database is ambient — the OPERATOR's, when the suite "
        "runs on their machine — and `runstate._reset_for_tests()` does NOT undo that (it clears the in-process "
        "cache only). Point `ZAELAR_DB` at a tmp_path, as `tests/agent_headless/unit/test_runstate.py` does:\n  "
        + "\n  ".join(offenders))


def test_the_ratchet_is_actually_watching_something():
    """A guard whose pattern stops matching passes forever while protecting nothing (the V2-201 lesson). If
    `runstate.stop()` is ever renamed, this fails and says so instead of going quietly green."""
    assert _persisting_test_files(), (
        "no test file calls runstate.stop/start/_persist any more — either that is a real change and this guard "
        "needs a new pattern, or the pattern has drifted away from the code it watches")
