"""An isolated workspace holds its OWN OAuth tokens (V2-781, 2026-10-09).

A use-case sandbox (`ZAELAR_WORKSPACE=<tmp>`) booted with the operator's Google Calendar connected: the calendar
token store was `<repo>/.meshkore/credentials/calendar_oauth.json`, fixed to the checkout, while settings, connectors
and the key store already followed the workspace. The EN round's «set a reminder» was written to his REAL calendar.
Every OAuth token store follows the workspace, like `config/credentials.py` and `meshkore/identity.py` already do.
"""
from __future__ import annotations

import importlib

import pytest

MODULES = ["connectors.calendar.oauth", "connectors.contacts.oauth", "connectors.email.oauth",
           "connectors.files.oauth", "connectors.photos.oauth", "connectors.video.oauth", "connectors.spotify.auth"]


@pytest.mark.parametrize("name", MODULES)
def test_the_token_store_lives_in_the_workspace(name, tmp_path, monkeypatch):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    mod = importlib.import_module(name)
    try:
        importlib.reload(mod)
        assert str(mod.STORE).startswith(str(tmp_path)), f"{name}.STORE = {mod.STORE} is outside the workspace"
    finally:
        monkeypatch.undo()
        importlib.reload(mod)
