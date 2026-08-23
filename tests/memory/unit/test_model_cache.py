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
    """La propiedad que importa: sea cual sea la casa, no puede ser un directorio que el sistema barre."""
    monkeypatch.delenv("ZAELAR_MODEL_CACHE", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path))

    d = model_cache.models_dir()

    assert d is not None
    p = pathlib.Path(d)
    assert p.is_dir(), "tiene que existir ya: crearla al vuelo es parte del contrato"
    assert "zaelar" in p.parts and "models" in p.parts
    # Sigue al HOME del usuario, que es lo que lo separa del temp del sistema. No se comprueba con una lista
    # de prefijos («/var/folders», «/tmp»): el tmp_path de pytest vive JUSTO ahí, así que esa comprobación se
    # ponía roja sobre el home falso del propio test — midiendo el andamio en vez del producto.
    assert str(p).startswith(str(tmp_path)), f"{p} no cuelga del HOME del usuario"


def test_la_casa_no_se_pide_al_modulo_de_temporales(monkeypatch, tmp_path):
    """Guarda de fuente, porque el defecto que se arregla es exactamente «usar el temp del sistema».

    El comportamiento no lo puede distinguir un test: con el HOME falsificado, `tempfile.gettempdir()` y un
    home real dan los dos una ruta plausible. Lo que se prohíbe es la FUENTE."""
    src = pathlib.Path(__import__("memory.model_cache", fromlist=["x"]).__file__).read_text(encoding="utf-8")
    codigo = src.split('"""', 2)[-1]        # fuera el docstring, que SÍ habla del temp para explicar el porqué
    for prohibido in ("tempfile", "gettempdir", "TMPDIR"):
        assert prohibido not in codigo, f"el cache de modelos volvió a resolverse por {prohibido}"


def test_respeta_XDG_CACHE_HOME(monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_MODEL_CACHE", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    d = model_cache.models_dir()
    assert d is not None and d.startswith(str(tmp_path / "xdg"))


def test_la_override_explicita_MANDA(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("ZAELAR_MODEL_CACHE", str(tmp_path / "mio"))
    d = model_cache.models_dir()
    assert d == str(tmp_path / "mio"), "quien la fija a mano tiene un motivo; nada la debe pisar"


def test_si_no_se_puede_crear_devuelve_None_y_no_LANZA(monkeypatch, tmp_path):
    """`None` es «sin opinión»: la librería usa su default. Lanzar aquí tumbaría el recall por un directorio."""
    choque = tmp_path / "es-un-fichero"
    choque.write_text("no soy un directorio")
    monkeypatch.setenv("ZAELAR_MODEL_CACHE", str(choque / "dentro"))
    assert model_cache.models_dir() is None


def test_los_DOS_consumidores_pasan_el_cache_y_ninguno_se_queda_con_el_default(monkeypatch):
    """Guarda de cableado: la mitad cara de este arreglo es que lo usen los DOS que descargan.

    Se comprueba en el CÓDIGO y no llamando: construir cualquiera de los dos baja gigabytes. Y son dos módulos
    distintos a propósito — arreglar solo el reranker deja el fallback de embeddings volviendo a frío, que es
    el mismo fallo con la mitad del tamaño y ninguna pista."""
    import ast

    raiz = pathlib.Path(__file__).resolve().parents[3]
    for fichero, ctor in (("memory/rerank_local.py", "TextCrossEncoder"),
                          ("memory/embeddings.py", "TextEmbedding")):
        src = (raiz / fichero).read_text(encoding="utf-8")
        # Por AST y NO buscando el texto: la primera vez este test buscó `"TextCrossEncoder("` con `.index()`
        # y encontró el DOCSTRING del módulo, que nombra el constructor para explicar el fallo. Salió rojo con
        # el arreglo puesto; podría igual de bien haber salido verde sin él.
        llamadas = [n for n in ast.walk(ast.parse(src))
                    if isinstance(n, ast.Call) and getattr(n.func, "id", None) == ctor]
        assert llamadas, f"{fichero} ya no construye {ctor}: este guarda mira al vacío"
        for c in llamadas:
            claves = {k.arg for k in c.keywords}
            assert "cache_dir" in claves or any(k.arg is None for k in c.keywords), (
                f"{fichero} construye {ctor} sin `cache_dir`: vuelve al TEMP del sistema y la purga se lo lleva")
        assert "model_cache" in src, f"{fichero} no resuelve la casa por `memory.model_cache`"
