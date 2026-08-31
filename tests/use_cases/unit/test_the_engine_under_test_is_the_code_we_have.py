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


# ── A harness commit is not a different engine ───────────────────────────────────────────────────────
# The guard refused on ANY different sha, and the engine and harness live in this tree: the harness
# commits several times an hour, so the run would stop to request a studio restart that would have
# measured exactly the same code. What matters is whether the PRODUCT moved.


def test_a_tests_only_commit_is_the_same_engine(monkeypatch):
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: False)
    assert run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"}) == ""


def test_a_tests_only_commit_still_SAYS_the_shas_differ(monkeypatch, capsys):
    """Continuing is not the same as staying silent. Without the line, the round report reads as though the
    studio is running exactly the current tree—and the next time a sha really diverges, no one will have
    anything to compare it with."""
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: False)
    run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"})
    out = capsys.readouterr().out
    assert "aaaaaaa" in out and "bbbbbbb" in out and "tests/" in out


def test_an_engine_commit_still_REFUSES(monkeypatch):
    """Sensitivity. Without this case, “does not refuse for tests” and “never refuses” both pass equally green."""
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: True)
    assert "no es el mismo codigo" in run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"})


def test_an_UNANSWERABLE_diff_refuses(monkeypatch):
    """`None` does not mean “nothing changed”: it is a sha this tree does not have (shallow clone, commit
    not fetched). In that case, retain the response that was safe before this function existed."""
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: None)
    assert "no es el mismo codigo" in run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"})


def test_the_diff_is_read_from_git_and_a_doc_counts_as_engine(tmp_path):
    """Against a REAL git repo, not a mock: what is being checked is that reading the tree works. And a
    change outside `tests/` counts EVEN if it is documentation—guessing which paths are inert is how a
    real change slips through."""
    import subprocess
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True)
    g("init", "-q")
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "a.py").write_text("x")
    g("add", "-A"); g("commit", "-qm", "one")
    base = g("rev-parse", "--short", "HEAD").stdout.strip()
    (tmp_path / "tests" / "a.py").write_text("y")
    g("add", "-A"); g("commit", "-qm", "solo tests")
    only_tests = g("rev-parse", "--short", "HEAD").stdout.strip()
    (tmp_path / "README.md").write_text("z")
    g("add", "-A"); g("commit", "-qm", "un doc")
    with_doc = g("rev-parse", "--short", "HEAD").stdout.strip()

    from tests.use_cases.e2e.agent import run as _R
    real = _R.__file__
    try:
        _R.__file__ = str(tmp_path / "a" / "b" / "c" / "d" / "run.py")   # parents[4] == tmp_path
        assert _R.engine_code_changed_between(base, only_tests) is False
        assert _R.engine_code_changed_between(only_tests, with_doc) is True
    finally:
        _R.__file__ = real


# ── A dirty tree does not contaminate a STUDIO ─────────────────────────────────────────────────────────
# It cost 23 minutes of a stalled run on 2026-08-21: another agent had `server/voice_api.py` uncommitted,
# and the round refused to run, even though the studio had had the code already loaded in memory since
# startup and was not going to read that file. The two questions are distinct, and only one determines
# what gets measured.


def test_the_lab_path_does_NOT_refuse_on_a_dirty_tree():
    """WIRING guard: inspect the source because the real path needs a live studio. A behavioral test here
    would require starting an engine, and without one the check does not exist."""
    import inspect
    src = inspect.getsource(run._lab_batch)
    assert "dirty_tree_refusal" not in src, "el camino del plató volvió a esperar por un árbol sucio"


def test_the_sandbox_path_STILL_refuses_on_a_dirty_tree():
    """Sensitivity, and it is the side that matters: in the sandbox the engine is started FROM THE TREE at
    that moment, so measuring there halfway through an edit really does measure partial code. Without
    this case, “do not wait in the studio” and “never wait” both pass equally green."""
    import inspect
    assert "dirty_tree_refusal" in inspect.getsource(run._sandbox_batch)


def test_a_stale_lab_exits_with_its_OWN_code():
    """The 5 exists so the caller can distinguish “restart the studio” from any other refusal. Sharing the 3
    made the run report “stale studio” for 23 minutes while something else was happening—an incorrect
    diagnosis, and a plausible one at that."""
    import inspect
    src = inspect.getsource(run._lab_batch)
    i = src.index("stale_engine_refusal(")
    assert "SystemExit(5)" in src[i:i + 700], "la negativa por motor rancio ya no sale con su propio código"
