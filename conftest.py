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
import os
import tempfile

os.environ.setdefault("ZAELAR_LOG_DIR", tempfile.mkdtemp(prefix="zaelar-test-logs-"))
