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
# ZAELAR_RESEARCH=0 — el DIRECTOR DE INVESTIGACIÓN (nucleo/research.py) compone el brief de una selección con una
# llamada REAL a un proveedor, en el pre-vuelo de cada escalada. En producción es lo que se quiere; en un test es
# una llamada de red no declarada que cuelga el caso hasta el timeout (visto con
# `test_listener_consumes_escalate_requested`: «busca un piso» es una investigación, así que el despacho se ponía
# a llamar al modelo). Apagado para toda la sesión de test; quien PRUEBE el compositor lo enciende a mano
# (monkeypatch) — la misma forma de knob que ZAELAR_LOG_DIR de arriba, y sin efecto en producción.
import os
import tempfile

os.environ.setdefault("ZAELAR_LOG_DIR", tempfile.mkdtemp(prefix="zaelar-test-logs-"))
os.environ.setdefault("ZAELAR_RESEARCH", "0")
