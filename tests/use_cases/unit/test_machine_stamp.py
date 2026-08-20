"""Two rounds are only comparable if the machine was, and until today the ledger said nothing about it.

2026-08-20: the memory agent's `scale_eval --fresh` held 39,2 GB in Ollama while a use-case round was being
measured, competing for the GPU with the sandbox's embeddings — the engine's local write model was paying a
TimeoutError per pill before failing over. The round was indistinguishable in the ledger from one measured on an
idle box, and it was only caught because that agent volunteered it. Honesty about a measurement cannot depend on
somebody happening to mention they were busy.

So the stamp RECORDS and does not judge: the local write titular is legitimately resident, and what matters is
that a reader comparing two rounds can see whether the box was the same.
"""
from __future__ import annotations

from tests.use_cases.e2e.agent import config


def test_it_records_what_is_resident(monkeypatch):
    out = ("NAME                     ID              SIZE      PROCESSOR    CONTEXT    UNTIL\n"
           "embeddinggemma:latest    85462619ee72    673 MB    100% GPU     2048       29 minutes from now\n"
           "qwen3.6:27b-mlx          60b0437bbd02    19 GB     100% GPU     32768      29 minutes from now\n")
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"stdout": out})())
    config._MACHINE_STAMP = None
    st = config.machine_stamp()
    assert st["n"] == 2
    assert {"name": "qwen3.6:27b-mlx", "size": "19 GB"} in st["gpu_models"]
    config._MACHINE_STAMP = None


def test_an_idle_machine_is_recorded_as_idle(monkeypatch):
    """The distinction the ledger needs: "nothing resident" must be a positive statement, not a gap."""
    import subprocess
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": "NAME  ID  SIZE  PROCESSOR\n"})())
    config._MACHINE_STAMP = None
    st = config.machine_stamp()
    assert st == {"gpu_models": [], "n": 0}
    config._MACHINE_STAMP = None


def test_no_ollama_never_costs_the_round(monkeypatch):
    """Fail-soft, same rule as every other stamp: bookkeeping must not be able to lose a measured round."""
    import subprocess

    def _boom(*a, **k):
        raise FileNotFoundError("no ollama")

    monkeypatch.setattr(subprocess, "run", _boom)
    config._MACHINE_STAMP = None
    st = config.machine_stamp()
    assert st["gpu_models"] == [] and st["n"] == 0 and "error" in st
    config._MACHINE_STAMP = None


def test_it_is_taken_once_per_process(monkeypatch):
    """The state that matters is the one at the start of the batch, and it must not cost a subprocess per case."""
    import subprocess
    calls = {"n": 0}

    def _run(*a, **k):
        calls["n"] += 1
        return type("R", (), {"stdout": "NAME  ID  SIZE  PROC\n"})()

    monkeypatch.setattr(subprocess, "run", _run)
    config._MACHINE_STAMP = None
    config.machine_stamp()
    config.machine_stamp()
    assert calls["n"] == 1
    config._MACHINE_STAMP = None
