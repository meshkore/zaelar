"""«Un selector de archivos para ver dónde el usuario quiere guardar los archivos de Zaelar» (V2-672).

The operator's brief for the first run: *«no le vamos a permitir ir por las carpetas diciendo a cuál le damos
permiso, sino que le podemos obligar a escoger una carpeta donde se van a guardar los archivos descargados,
generados, etc. Eso sí que podría ser el paso número dos… También hay que poner un botón de skip.»*

THIS IS A NEW SECURITY SEAM AND THAT IS THE POINT OF THE FILE. `library/paths.resolve()` refuses absolute
paths on purpose — everything reaching it comes from magnet payloads, model output and query strings. The
folder step cannot reuse it: it needs to ACCEPT an absolute path. So it is a second door with a different
provenance (a person, on their own machine, once) and its own validator, and what is measured here is that
the validator REFUSES rather than repairs — the V2-575 daemon rule: never silently reinterpret a path.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def api():
    from library.server_api import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolated_overrides(tmp_path, monkeypatch):
    """Never write the operator's real config/library.json from a unit test."""
    from library import paths
    store = tmp_path / "library.json"
    monkeypatch.setattr(paths, "_overrides_path", lambda: store)
    paths._ov_cache.update(path=None, mtime=None, data={})
    yield store
    paths._ov_cache.update(path=None, mtime=None, data={})


# ── the validator refuses, and names what it refused ──────────────────────────────────────────────────────

def test_a_relative_path_is_refused_and_never_reinterpreted():
    from library import paths
    got = paths.check_base("somewhere/else")
    assert got["ok"] is False and got["reason"] == "not_absolute"


def test_a_folder_that_does_not_exist_is_refused_rather_than_created(tmp_path):
    """"I'll make it for you" turns a typo into a folder tree in a place nobody meant."""
    from library import paths
    target = tmp_path / "nope"
    got = paths.check_base(str(target))
    assert got["ok"] is False and got["reason"] == "missing"
    assert not target.exists(), "a refusal must not have side effects"


def test_a_file_is_not_a_folder(tmp_path):
    from library import paths
    f = tmp_path / "a.txt"
    f.write_text("x", encoding="utf-8")
    assert paths.check_base(str(f))["reason"] == "not_a_directory"


def test_the_whole_machine_is_never_a_library():
    """Root and HOME are both "everything", and a library that broad makes `resolve()`'s boundary — which
    exists to keep untrusted paths inside the library — mean nothing."""
    from library import paths
    assert paths.check_base(os.path.abspath(os.sep))["reason"] == "filesystem_root"
    assert paths.check_base(str(Path.home()))["reason"] == "home_itself"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX system paths")
def test_a_system_directory_is_refused():
    from library import paths
    assert paths.check_base("/etc")["reason"] == "system_directory"


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX symlinks")
def test_a_symlink_cannot_smuggle_a_forbidden_folder_past_the_check(tmp_path):
    """The check is made on the RESOLVED path — the same rule `resolve()` follows, for the same reason."""
    from library import paths
    link = tmp_path / "innocent"
    link.symlink_to("/etc")
    assert paths.check_base(str(link))["reason"] == "system_directory"


def test_a_real_writable_folder_is_accepted_and_reported_resolved(tmp_path):
    from library import paths
    got = paths.check_base(str(tmp_path))
    assert got["ok"] is True
    assert Path(got["path"]) == tmp_path.resolve(), "the stored path is the resolved one, never the raw text"


# ── what the choice actually moves ────────────────────────────────────────────────────────────────────────

def test_choosing_a_folder_moves_the_whole_tree_under_it(tmp_path):
    from library import paths
    paths.set_overrides({"base": str(tmp_path)})
    assert paths.base() == tmp_path.resolve()
    assert paths.root().parent == tmp_path.resolve()
    assert paths.root().name, "the library keeps a NAME of its own under the chosen folder"
    assert paths.dir_for("downloads").is_relative_to(tmp_path.resolve())


def test_the_library_keeps_its_own_folder_instead_of_scattering_into_his(tmp_path):
    """Five kind-folders dropped straight into somebody's Documents is not a choice they made."""
    from library import paths
    paths.set_overrides({"base": str(tmp_path)})
    assert paths.root() != tmp_path.resolve()
    assert paths.root().parent == tmp_path.resolve()


def test_an_empty_value_is_the_way_back_to_the_default(tmp_path):
    from library import paths
    paths.set_overrides({"base": str(tmp_path)})
    assert paths.base() == tmp_path.resolve()
    paths.set_overrides({"base": ""})
    from nucleo import workspace as ws
    assert paths.base() == ws.root(), "a chosen folder must be undoable, or it is a trap"


def test_a_stored_folder_that_stopped_existing_falls_back_instead_of_writing_into_nowhere(tmp_path):
    """The disk is unplugged, the folder was deleted. Writing to a stale absolute path is worse than using
    the place that always exists — so `base()` re-validates on every read."""
    from library import paths
    gone = tmp_path / "usb"
    gone.mkdir()
    paths.set_overrides({"base": str(gone)})
    assert paths.base() == gone.resolve()
    gone.rmdir()
    from nucleo import workspace as ws
    assert paths.base() == ws.root()


def test_a_refused_folder_is_never_persisted(tmp_path, _isolated_overrides):
    from library import paths
    paths.set_overrides({"base": str(tmp_path)})
    res = paths.set_overrides({"base": "/etc"})
    assert res["ok"] is False and res["reason"] == "system_directory"
    assert paths.base() == tmp_path.resolve(), "a refusal must leave the previous choice standing"


# ── the HTTP surface, and the deployment that may not be asked ────────────────────────────────────────────

def test_the_endpoint_says_where_the_files_go_and_whether_a_picker_can_be_drawn(api, monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    got = api.get("/api/library/base").json()
    assert got["ok"] and got["base"] and got["root"]
    assert got["can_choose"] is True
    assert isinstance(got["has_dialog"], bool), (
        "the modal needs to know whether to offer a picker or a typed path — not guess")


def test_a_cloud_account_is_never_asked_where_to_put_its_files(api, monkeypatch, tmp_path):
    """There the Volume IS the storage and the process has no desktop to draw a dialog on. Offering the
    question would be offering a choice that cannot be honoured."""
    monkeypatch.setenv("ZAELAR_USER_ID", "usr_real_account")
    assert api.get("/api/library/base").json()["can_choose"] is False
    assert api.post("/api/library/base", json={"base": str(tmp_path)}).status_code == 403
    assert api.post("/api/library/base/browse").status_code == 403


def test_a_bad_folder_comes_back_with_a_reason_the_screen_can_show(api, monkeypatch):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    r = api.post("/api/library/base", json={"base": "/etc"})
    assert r.status_code == 400
    assert r.json()["reason"] == "system_directory", (
        "a refusal the person cannot act on reads as a broken product (V2-559)")


def test_choosing_through_the_endpoint_creates_the_tree_so_the_choice_is_visible(api, monkeypatch, tmp_path):
    monkeypatch.delenv("ZAELAR_USER_ID", raising=False)
    got = api.post("/api/library/base", json={"base": str(tmp_path)}).json()
    assert got["ok"]
    assert Path(got["root"]).is_dir(), "the folder he picked should contain the tree the moment he picks it"


# ── the native dialog is BEST EFFORT and says so ──────────────────────────────────────────────────────────

def test_no_picker_on_this_machine_is_a_normal_answer_not_a_failure(monkeypatch):
    """A headless box, a container, an SSH session. The caller falls back to a typed path, which goes through
    the SAME validator — so nothing depends on which door was used."""
    from library import folder_dialog
    monkeypatch.setattr(folder_dialog, "available", lambda: False)
    assert folder_dialog.choose() == {"ok": False, "reason": "unavailable"}


def test_a_cancelled_dialog_is_reported_as_cancelled(monkeypatch):
    """He opened the picker and closed it. Painting a failure over a deliberate non-answer is wrong, and the
    step has a «skip» precisely because not answering is allowed."""
    import subprocess
    from library import folder_dialog

    class _Done:
        returncode = 1
        stdout = ""
    monkeypatch.setattr(folder_dialog, "available", lambda: True)
    monkeypatch.setattr(folder_dialog, "_argv", lambda prompt: ["true"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Done())
    assert folder_dialog.choose()["reason"] == "cancelled"


def test_what_the_dialog_returns_still_goes_through_the_validator(monkeypatch):
    """A picker is a convenience, not an authority: whatever it hands back is validated like typed text."""
    import subprocess
    from library import folder_dialog

    class _Done:
        returncode = 0
        stdout = "/etc\n"
    monkeypatch.setattr(folder_dialog, "available", lambda: True)
    monkeypatch.setattr(folder_dialog, "_argv", lambda prompt: ["true"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _Done())
    assert folder_dialog.choose() == {"ok": False, "reason": "system_directory"}
