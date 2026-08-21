"""A clean tree does not mean an up-to-date process, and the difference costs whole batches.

2026-08-21: the lab agent had been up since 12:47 on `3.15+4abaf9c` while four commits landed on top of
it. `dirty_tree_refusal` was happy — nobody was mid-edit — so every round of the afternoon measured code
that no longer existed. One verdict was about to be reported to the engine agent as a regression in a
feature he had just shipped and that the running process had never loaded.

These tests pin the guard AND its deliberate soft edge: an unreadable version warns, it does not refuse.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.use_cases.e2e.agent import run  # noqa: E402


def test_a_stale_process_refuses_the_round(monkeypatch):
    monkeypatch.setattr(run, "running_engine_sha", lambda _u: "4abaf9c")
    msg = run.stale_engine_refusal("http://x", {"sha": "f3052f9"})
    assert msg and "4abaf9c" in msg and "f3052f9" in msg


def test_the_same_code_goes_ahead(monkeypatch):
    monkeypatch.setattr(run, "running_engine_sha", lambda _u: "f3052f9")
    assert run.stale_engine_refusal("http://x", {"sha": "f3052f9"}) == ""


def test_different_sha_LENGTHS_are_the_same_code(monkeypatch):
    """`/api/status` and `git rev-parse --short` do not have to agree on how many characters a short sha
    has. Comparing them with `!=` would refuse every single round while looking like a real finding."""
    monkeypatch.setattr(run, "running_engine_sha", lambda _u: "f3052f9abc")
    assert run.stale_engine_refusal("http://x", {"sha": "f3052f9"}) == ""


def test_an_unreadable_version_WARNS_instead_of_blocking(monkeypatch):
    """Deliberate soft edge: refusing on "I could not ask" would block every round the moment
    `/api/status` changes shape. The round still has value; silence is what did the damage."""
    monkeypatch.setattr(run, "running_engine_sha", lambda _u: "")
    assert run.stale_engine_refusal("http://x", {"sha": "f3052f9"}) == ""
    monkeypatch.setattr(run, "running_engine_sha", lambda _u: "4abaf9c")
    assert run.stale_engine_refusal("http://x", {"sha": ""}) == ""


def test_the_reader_survives_an_engine_that_is_not_there():
    """A port with nothing behind it must return "" and not raise: an exception here kills the round
    before it starts, which is a worse outcome than measuring without knowing the sha."""
    assert run.running_engine_sha("http://127.0.0.1:1") == ""


def test_the_lab_path_actually_calls_the_guard():
    """The counterweight that matters. A guard that exists and is never wired in reads, from the outside,
    exactly like a guard that works — which is the shape of this very bug."""
    import inspect
    src = inspect.getsource(run._lab_batch)
    assert "stale_engine_refusal" in src, "la guarda no está cableada en la ruta de plató"
    assert src.index("stale_engine_refusal") < src.index("config.ZAELAR_URL"), \
        "la guarda tiene que correr ANTES de apuntar el arnés al motor"
