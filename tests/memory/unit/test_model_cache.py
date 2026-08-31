"""The local ONNX models must NOT live in the system TEMP directory (2026-08-23).

Found while verifying a claim of my own that turned out to be wrong. I had reported — to a teammate and in a
commit message — that the cross-encoder was "not on this machine", after looking in `~/.cache/fastembed` and
the HuggingFace hub. Both were empty and the model was there all along: `fastembed` caches into the system
TEMP dir, which is where 1.8 GB were sitting (cross-encoder + the embedding fallback), downloaded that same
day at 12:22 — the download that hung the memory suite for the session before this one.

That makes the real defect worse than the one I described, not milder: TEMP is swept periodically by the OS
and vanishes outright when a container stops, so the download is NOT a one-time install cost. It comes back,
on a machine that already had the model, at whatever moment the sweep runs — and what the operator
experiences is recall going cold again for no visible reason, with gigabytes hidden somewhere nothing under
`~` or in the repo would show.

These tests pin the three properties that fix depends on. They never construct a model (downloading a
gigabyte is not a unit test): the contract under test is WHERE we tell the library to put it.
"""
from __future__ import annotations

import pathlib

from memory import model_cache


def test_por_defecto_NO_cae_en_el_temp_del_sistema(monkeypatch, tmp_path):
    """The property that matters: whatever the home directory is, it cannot be a directory the system sweeps."""
    monkeypatch.delenv("ZAELAR_MODEL_CACHE", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

    d = model_cache.models_dir()

    assert d is not None
    p = pathlib.Path(d)
    assert p.is_dir(), "it must already exist: creating it on the fly is part of the contract"
    assert "zaelar" in p.parts and "models" in p.parts
    # It follows the user's HOME, which is what separates it from the system temp directory. We do not check
    # against a list of prefixes ("/var/folders", "/tmp"): pytest's tmp_path lives RIGHT there, so that check
    # turned red for the test's own fake home—measuring the scaffolding instead of the product.
    assert str(p).startswith(str(tmp_path)), f"{p} is not under the user's HOME"


def test_la_casa_no_se_pide_al_modulo_de_temporales(monkeypatch, tmp_path):
    """Source-level guard, because the defect being fixed is exactly “use the system temp directory.”

    A test cannot distinguish the behavior: with the HOME falsified, `tempfile.gettempdir()` and a real home
    both produce a plausible path. What is prohibited is the SOURCE."""
    src = pathlib.Path(__import__("memory.model_cache", fromlist=["x"]).__file__).read_text(encoding="utf-8")
    codigo = src.split('"""', 2)[-1]        # exclude the docstring, which DOES mention temp to explain why
    for prohibido in ("tempfile", "gettempdir", "TMPDIR"):
        assert prohibido not in codigo, f"the model cache started resolving through {prohibido} again"


def test_respeta_XDG_CACHE_HOME(monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_MODEL_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    d = model_cache.models_dir()
    assert d is not None and d.startswith(str(tmp_path / "xdg"))


def test_la_override_explicita_MANDA(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("ZAELAR_MODEL_CACHE", str(tmp_path / "mio"))
    d = model_cache.models_dir()
    assert d == str(tmp_path / "mio"), "whoever sets it manually has a reason; nothing should override it"


def test_si_no_se_puede_crear_devuelve_None_y_no_LANZA(monkeypatch, tmp_path):
    """`None` means “no opinion”: the library uses its default. Raising here would break recall because of a directory."""
    choque = tmp_path / "es-un-fichero"
    choque.write_text("no soy un directorio")
    monkeypatch.setenv("ZAELAR_MODEL_CACHE", str(choque / "dentro"))
    assert model_cache.models_dir() is None


def test_los_DOS_consumidores_pasan_el_cache_y_ninguno_se_queda_con_el_default(monkeypatch):
    """Wiring guard: the expensive half of this fix is making sure that BOTH downloaders use it.

    This is checked in the CODE rather than by calling it: constructing either one downloads gigabytes. They are
    deliberately two different modules—fixing only the reranker leaves the embedding fallback going cold again,
    which is the same failure at half the size and with no clue."""
    import ast

    raiz = pathlib.Path(__file__).resolve().parents[3]
    for fichero, ctor in (("memory/rerank_local.py", "TextCrossEncoder"),
                          ("memory/embeddings.py", "TextEmbedding")):
        src = (raiz / fichero).read_text(encoding="utf-8")
        # Use the AST and do NOT search the text: the first version of this test searched for
        # `"TextCrossEncoder("` with `.index()` and found the module DOCSTRING, which names the constructor to
        # explain the failure. It turned red with the fix in place; it could just as easily have turned green
        # without it.
        llamadas = [n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.Call) and getattr(n.func, "id", None) == ctor]
        assert llamadas, f"{fichero} no longer constructs {ctor}: this guard is looking at nothing"
        for c in llamadas:
            claves = {k.arg for k in c.keywords}
            assert "cache_dir" in claves or any(k.arg is None for k in c.keywords), (
                f"{fichero} constructs {ctor} without `cache_dir`: it falls back to the system TEMP and the purge takes it away")
        assert "model_cache" in src, f"{fichero} does not resolve the home through `memory.model_cache`"
