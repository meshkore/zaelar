from pathlib import Path

from nucleo import workspace


def test_root_unset_falls_back_to_repo_root(monkeypatch):
    monkeypatch.delenv("ZAELAR_WORKSPACE", raising=False)
    assert workspace.root() == workspace._REPO_ROOT


def test_root_set_returns_that_path(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    assert workspace.root() == tmp_path


def test_root_set_blank_falls_back_to_repo_root(monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", "   ")
    assert workspace.root() == workspace._REPO_ROOT


def test_repo_root_is_engine_dir():
    # engine/nucleo/workspace.py -> parent (nucleo) -> parent (engine)
    assert workspace._REPO_ROOT.name == "engine"
    assert (workspace._REPO_ROOT / "nucleo").is_dir()


def test_memory_db_path_matches_workspace_when_set(monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_DB", raising=False)
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from memory import db as _db

    assert _db.db_path() == tmp_path / "memory" / "_data" / "zaelar.db"


def test_memory_db_path_unchanged_when_unset(monkeypatch):
    monkeypatch.delenv("ZAELAR_DB", raising=False)
    monkeypatch.delenv("ZAELAR_WORKSPACE", raising=False)
    from memory import db as _db

    assert _db.db_path() == workspace._REPO_ROOT / "memory" / "_data" / "zaelar.db"


def test_widgets_store_data_dir_moves_with_workspace(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    import importlib

    from widgets import store as _store

    # V2-194: session isolation (`conftest.py` points `DATA_DIR` to a temporary directory so that no test
    # writes to the operator's REAL data) lives in a MODULE variable, and a `reload` recomputes it
    # from the actual workspace. In other words, the `reload` below—added to “restore the module's
    # state”—was exactly what reopened the leak for everything that ran afterward. It is saved and restored.
    _isolated = _store.DATA_DIR
    importlib.reload(_store)
    try:
        assert Path(_store.DATA_DIR) == tmp_path / "widgets" / "_data"
    finally:
        monkeypatch.delenv("ZAELAR_WORKSPACE", raising=False)
        importlib.reload(_store)  # restore module state for any test that runs after this one
        _store.DATA_DIR = _isolated          # …including the isolation, which the reload wipes out


def test_credentials_store_unchanged_when_workspace_unset(monkeypatch):
    monkeypatch.delenv("ZAELAR_WORKSPACE", raising=False)
    from config import credentials

    assert credentials._store_path() == credentials._ROOT / ".meshkore" / "credentials" / "zaelar.env"


def test_credentials_store_drops_meshkore_segment_when_workspace_set(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from config import credentials

    assert credentials._store_path() == tmp_path / "credentials" / "zaelar.env"
