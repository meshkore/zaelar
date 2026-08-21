"""A worker whose bridges are denied is not a product failure — and it reads exactly like one.

MEASURED 2026-08-21 on the pinned measuring worktree: every `python -m nucleo.<bridge>` call came back
«This command requires approval», in headless where nobody approves. The worker said so precisely — «el
entorno donde estoy corriendo ha bloqueado todas las herramientas… aquí nadie puede aprobarlas» — and the
judge's top finding became «zaelar afirmó haber localizado opciones cuando el entorno bloqueó TODAS las
herramientas». The blockade belonged to the measuring rig: `_BRIDGE_TOOLS` is built from `_ZAELAR`
(`__file__` → the worktree) while the prompt hands the worker `bridge_python()` (`sys.executable` → the real
venv, because Python resolves a symlinked `.venv`). Five earlier rounds carried it: every worktree round that
spawned a worker shows 18-27 denials.
"""
from __future__ import annotations

from nucleo.workers import claude_session as cs
from tests.use_cases.e2e.agent import run as R


def test_a_matching_interpreter_measures(monkeypatch):
    monkeypatch.setattr(cs, "_INTERPRETERS", ("python", "/real/.venv/bin/python"))
    monkeypatch.setattr(cs, "bridge_python", lambda: "/real/.venv/bin/python")
    assert R.bridge_allowlist_refusal() == ""


def test_the_worktree_mismatch_REFUSES_and_shows_BOTH_paths(monkeypatch):
    """Naming only one side leaves the reader guessing which of the two moved."""
    monkeypatch.setattr(cs, "_INTERPRETERS", ("python", "/worktree/.venv/bin/python"))
    monkeypatch.setattr(cs, "bridge_python", lambda: "/real/.venv/bin/python")
    out = R.bridge_allowlist_refusal()
    assert "NO ESTÁN PERMITIDOS" in out
    assert "/real/.venv/bin/python" in out and "/worktree/.venv/bin/python" in out
    assert "requires approval" in out, "hay que nombrar el síntoma para que se reconozca en un log"


def test_it_reads_the_SAME_values_production_reads(monkeypatch):
    """A copy of the rule is a second place to drift — and drifting silently is the whole defect here."""
    called = {}
    monkeypatch.setattr(cs, "bridge_python", lambda: called.setdefault("py", "/x") or "/x")
    monkeypatch.setattr(cs, "_INTERPRETERS", ("/x",))
    assert R.bridge_allowlist_refusal() == ""
    assert called.get("py") == "/x", "debe preguntar a bridge_python, no reconstruir la ruta"


def test_a_broken_check_does_NOT_block_the_round(monkeypatch):
    """Not being able to CHECK the lock is not the same as knowing it is shut. A round lost to a guard that
    broke itself is worse than the round it meant to protect."""
    def boom():
        raise RuntimeError("nope")
    monkeypatch.setattr(cs, "bridge_python", boom)
    assert R.bridge_allowlist_refusal() == ""
