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


# ── Un commit del ARNÉS no es un motor distinto ───────────────────────────────────────────────────────
# La guarda refusaba ante CUALQUIER sha distinto, y en este árbol viven el motor y el arnés: el arnés
# commitea varias veces por hora, así que el paseo se paraba a pedir un reinicio del plató que habría
# medido exactamente el mismo código. Lo que decide es si se movió el PRODUCTO.


def test_a_tests_only_commit_is_the_same_engine(monkeypatch):
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: False)
    assert run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"}) == ""


def test_a_tests_only_commit_still_SAYS_the_shas_differ(monkeypatch, capsys):
    """Seguir no es callarse. Sin la línea, el informe de la ronda se lee como que el plató corre justo el
    árbol que hay — y la próxima vez que un sha desencaje de verdad nadie tendrá con qué compararlo."""
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: False)
    run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"})
    out = capsys.readouterr().out
    assert "aaaaaaa" in out and "bbbbbbb" in out and "tests/" in out


def test_an_engine_commit_still_REFUSES(monkeypatch):
    """Sensibilidad. Sin este caso, «no refuses por tests» y «no refuses nunca» pasan igual de verdes."""
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: True)
    assert "no es el mismo codigo" in run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"})


def test_an_UNANSWERABLE_diff_refuses(monkeypatch):
    """`None` no es «no cambió nada»: es un sha que este árbol no tiene (clon superficial, commit sin
    traer). Ante eso se conserva la respuesta que era segura antes de existir esta función."""
    monkeypatch.setattr(run, "running_engine_sha", lambda url: "aaaaaaa")
    monkeypatch.setattr(run, "engine_code_changed_between", lambda a, b: None)
    assert "no es el mismo codigo" in run.stale_engine_refusal("http://x", {"sha": "bbbbbbb"})


def test_the_diff_is_read_from_git_and_a_doc_counts_as_engine(tmp_path):
    """Contra un repo git REAL, no contra un mock: lo que se comprueba es que la lectura del árbol
    funciona. Y un cambio fuera de `tests/` cuenta AUNQUE sea documentación — adivinar qué rutas son
    inertes es como se cuela un cambio real."""
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
