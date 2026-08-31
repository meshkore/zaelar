# Root pytest conftest — test isolation for shared runtime state.
#
# Several unit tests exercise modules that, in production, write to the SINGLE live MeshKore log dir
# (.meshkore/logs/): voice/observer.py::emit() appends to timeline-latest.jsonl, and tests like
# tests/infrastructure/integration/test_sse_observer.py ("error"/"boom"/"oops") or
# tests/connectors/unit/architect/test_architect.py drive that path
# directly. Without isolation those synthetic events land in the very file the running server + the operator's
# audits read for REAL post-mortems — a test's "kind:error boom" is then indistinguishable from a live incident
# (exactly what happened 2026-07-25). Point ZAELAR_LOG_DIR at a throwaway dir for the whole test session BEFORE
# any module reads it at import time. Same knob shape as bus/log.py's ZAELAR_DB / nucleo/workspace.py's
# ZAELAR_WORKSPACE; unset in production → byte-identical to before.
#
# ZAELAR_RESEARCH=0 — the RESEARCH DIRECTOR (nucleo/research.py) composes a selection brief with a REAL
# provider call during escalation preflight. That is wanted in production; in a test it is
# an undeclared network call that hangs the case until timeout (seen with
# `test_listener_consumes_escalate_requested`: «busca un piso» is research, so dispatch started calling the model).
# Disabled for the whole test session; anyone TESTING the composer enables it manually
# (monkeypatch) — the same knob pattern as ZAELAR_LOG_DIR above, with no production effect.
#
# ZAELAR_LANGUAGE=en — THE TEST RUNNER'S MACHINE MUST NOT CHOOSE THE LANGUAGE (2026-08-10). Two tests were green
# because of the ENVIRONMENT rather than the code (`test_music_flow`, `test_prompt`): they checked phrases spoken to
# the operator without fixing the language, so they passed on a Spanish-configured machine and would fail elsewhere
# and in CI. That is the worst kind of test — it does not fail; it LIES about what it covers.
# The product's STARTUP language (`langs.DEFAULT_LANG`, English) is fixed here, matching every new installation;
# a test for another language declares it itself (monkeypatch), making its coverage explicit. Thus the operator's
# `config/settings.json` can no longer change the suite result.
import os
import tempfile

os.environ.setdefault("ZAELAR_LOG_DIR", tempfile.mkdtemp(prefix="zaelar-test-logs-"))
os.environ.setdefault("ZAELAR_RESEARCH", "0")
# FORCED, not `setdefault`: with a default, `ZAELAR_LANGUAGE=es` in the suite runner's shell would again
# change what «green» means, which is exactly the problem. A test's language is declared by THE TEST (monkeypatch),
# and both languages are tested INSIDE the case —as with the memory-layer guard—, rather than running the suite twice
# with a changed environment.
os.environ["ZAELAR_LANGUAGE"] = "en"

# …AND THE OPERATOR'S CONFIG MUST NOT DECIDE THE SUITE RESULT (2026-08-10).
#
# Fixing `ZAELAR_LANGUAGE` above is NOT enough, and discovering that is the finding: `config/settings.load_into_env()` copies
# `config/settings.json` OVER the environment (`os.environ[env] = ...`, unconditionally) because in production the
# store OVERRIDES the env — the correct rule there. In a test, once anything in the import graph calls that function,
# the operator's language (here `es`) overwrites the suite's… along with the STT/TTS provider, attention mode, and
# engine profile. A test can therefore be green because of the machine where it runs.
# It surfaced through language (two tests checked Spanish phrases without fixing it: green here, red in CI), but
# the class of issue is broader than language.
#
# The settings file is pointed to an EMPTY temporary file for the whole test session, at module level rather than in a
# fixture, because test modules are imported BEFORE any fixture runs. Same isolation lesson
# like ZAELAR_LOG_DIR above, ZAELAR_DB in bus/log.py, and `store.DATA_DIR` in widget tests: **a test never
# never reads or writes the operator's real state**. Anyone genuinely testing `load_into_env` points it at their own file.
try:
    from pathlib import Path as _Path

    from config import settings as _settings

    _settings.SETTINGS_FILE = _Path(tempfile.mkdtemp(prefix="zaelar-test-settings-")) / "settings.json"
except Exception:                                  # if `config` is not importable, the suite continues as before
    pass

# V2-194 — the SAME invariant as above («a test never reads or writes the operator's real state»),
# applied to the last place still missing: widget DATA. The comment above already cited
# `store.DATA_DIR` as the same lesson, but it was applied only inside widget tests, not at session level
# — so any other test dispatching a data-op wrote to the REAL agenda.
#
# Measured on 2026-08-20: **328 appointments** «renovar el seguro del coche» accumulated in the operator's agenda, and
# **2 more per complete suite run**. Nothing failed: the garbage remained there and was noticed only
# when someone looks at the agenda — or when a new fix starts READING IT (V2-194 appointment deduplication) and
# suddenly nine tests depend on the order in which earlier tests ran.
try:
    from widgets import store as _wstore

    _wstore.DATA_DIR = _Path(tempfile.mkdtemp(prefix="zaelar-test-widgets-"))
except Exception:                                  # if `widgets` is not importable, the suite continues as before
    pass


# V2-279 — AN OPEN TRACE LEAKS INTO SUBSEQUENT TESTS (2026-08-24).
#
# `voice/trace.begin()` sets a ContextVar and has NO teardown: pytest runs the whole suite in one context,
# so a test that opens a trace and does not close it leaves it set for all subsequent tests. Measured: running
# `tests/infrastructure/unit` before `tests/agent_headless/unit` makes
# `test_escalate_registers_and_emits_bus` fail; it compares the escalation `context` with `{"src": "voice"}` and
# receives `{"src": "voice", "trace": "T1·7d5a"}` — ANOTHER test's trace, sealed by `escalate_to_slowbrain`
# doing exactly what it should. Running the suite alone is green.
#
# The class of issue is worse than that case: `observer.emit` reads the trace on EVERY event, so any test
# can be attributed to another test's trace. It is also order-dependent, appearing or disappearing depending on
# which testmap nodes run together — the most expensive failure because it cannot be reproduced when investigated.
#
# The ContextVar is reset in the teardown of EACH test. Deliberately WITHOUT `monkeypatch`: a fixture in the
# ROOT conftest that requests it would reorder teardown for the entire suite (already causing an ERROR in an untouched
# test). Anyone TESTING the trace opens it inside their own case, as the two files using it already do.
try:
    import pytest as _pytest

    from voice import trace as _trace

    @_pytest.fixture(autouse=True)
    def _no_trace_leaks_between_tests():
        yield
        try:
            _trace._ctx.set(("", ""))
        except Exception:
            pass
except Exception:                                  # sin `voice` importable, la suite sigue como antes
    pass
