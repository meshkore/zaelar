"""The contacts test set (V2-854): every case runs on the SYNTHETIC directory, in an isolated store."""
from __future__ import annotations

import pytest

from . import directory_fixture


@pytest.fixture
def directory_world(tmp_path, monkeypatch):
    """An ISOLATED contacts + messaging store holding the synthetic directory — never the operator's real one.
    Yields `(contacts data module, directory module, rows)`."""
    from widgets import store
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    from widgets import directory
    from widgets.contactos import data as cd
    directory._WINDOW.clear()
    directory._ASKED.clear()
    rows = directory_fixture.install(store, cd)
    yield cd, directory, rows
    directory._WINDOW.clear()
    directory._ASKED.clear()
