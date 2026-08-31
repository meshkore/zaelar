"""Restore: discard the fork / unhide, come back to the NEWEST shipped version (V2-515, phase 4).

The shipped folder is never touched while shadowed — engine updates keep landing on it — so restore
always returns the latest system version, not the one the fork was cut from. The verb resolves against
what is RESTORABLE (forks + hidden shipped widgets): a deleted widget is out of the catalog, which is
exactly why `runtime.identify` cannot be the resolver here.

Every confirmation class must also execute from the card's Yes/No BUTTON: resolve() consumes the
pending before the dispatch branches, so a class the endpoint does not know destroys the confirmation
and executes nothing (the measured 2026-08-15 `data` incident). `restore` gets that test on day one.
"""
from __future__ import annotations

import asyncio
import json
import os

import pytest

from widgets import confirm, hidden, lifecycle, paths, runtime


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(lifecycle, "_mem_write", lambda text, importance: None)
    monkeypatch.setattr(lifecycle, "_emit_widget", lambda action, w, src="system": None)
    confirm.reset()
    runtime.invalidate()
    yield tmp_path
    hidden.unhide("clock")
    paths.forget_modules("clock")
    runtime.invalidate()


def _fork_clock(tmp_path) -> str:
    folder = tmp_path / "widgets" / "clock"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps(
        {"id": "clock", "title": "Mi reloj", "keywords": ["reloj"], "origin": "user",
         "forked_from": {"origin": "builtin"}}), encoding="utf-8")
    (folder / "widget.js").write_text("export function render(){} // customized", encoding="utf-8")
    runtime.invalidate()
    return str(folder)


def test_restoring_a_forked_widget_discards_the_fork(lab):
    fork = _fork_clock(lab)
    assert paths.dir_for("clock") == fork                       # the fork is what the catalog serves…
    res = asyncio.run(lifecycle.restore_widget("clock"))
    assert res["ok"] is True and res["discarded_fork"] is True
    assert not os.path.isdir(fork)
    assert paths.dir_for("clock") == os.path.join(paths.BUILTIN_ROOT, "clock")   # …and now the shipped one is back


def test_restoring_a_hidden_widget_unhides_it(lab):
    hidden.hide("clock")
    runtime.invalidate()
    assert "clock" not in {w.get("id") for w in runtime.catalog()}
    res = asyncio.run(lifecycle.restore_widget("clock"))
    assert res["ok"] is True and res["discarded_fork"] is False
    assert "clock" not in hidden.ids()
    assert "clock" in {w.get("id") for w in runtime.catalog()}


def test_a_purely_user_widget_has_nothing_to_restore_to(lab):
    folder = lab / "widgets" / "tmptest-solo-mio"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(json.dumps({"id": "tmptest-solo-mio"}), encoding="utf-8")
    (folder / "widget.js").write_text("export function render(){}", encoding="utf-8")
    runtime.invalidate()
    res = asyncio.run(lifecycle.restore_widget("tmptest-solo-mio"))
    assert res["ok"] is False
    assert os.path.isdir(folder)                                # and it did NOT delete the user's widget


def test_restorable_id_sees_what_identify_cannot(lab):
    assert lifecycle.restorable_id("restaura el clock") == ""   # nothing forked, nothing hidden → nothing restorable
    hidden.hide("clock")
    runtime.invalidate()
    assert lifecycle.restorable_id("clock") == "clock"          # exact id
    man = json.load(open(os.path.join(paths.BUILTIN_ROOT, "clock", "manifest.json"), encoding="utf-8"))
    alias = next((str(k) for k in (man.get("aliases") or man.get("keywords") or []) if str(k).strip()), "")
    if alias:
        assert lifecycle.restorable_id(f"quiero recuperar {alias}") == "clock"   # by the SHIPPED manifest's words


def test_the_registry_flags_a_fork_so_the_ui_can_offer_restore(lab):
    from widgets import registry
    _fork_clock(lab)
    row = next(r for r in registry.registry() if r["id"] == "clock")
    assert row["forked"] is True and row["origin"] == "user"


def test_the_yes_button_executes_a_restore_confirmation(lab):
    """The 2026-08-15 class-gap rule: a confirmation class the button endpoint does not dispatch consumes
    the pending and executes NOTHING. The restore class must execute from the card's Yes button."""
    from widgets import server_api
    fork = _fork_clock(lab)
    confirm.request("restore", "clock", "¿Vuelvo el widget a la versión de sistema?")
    resp = asyncio.run(server_api.confirm_widget("clock", {"ok": True}))
    body = json.loads(bytes(resp.body))
    assert body["ok"] is True
    assert not os.path.isdir(fork)                              # the Yes actually restored
