"""V2-557 — the LIVE round trip against a real cloud drive. Credential-gated: SKIPS until one is connected.

This is the half the deterministic suite structurally cannot cover. Everything below the seam is HTTP against
somebody's real account, and a fake that answers the way we THINK Drive answers proves only that we agree with
ourselves — the lesson this engine has paid for repeatedly («integración viva no se da por buena con mocks»).

## Why it is a `live` node and not a skipped unit test

A node marked `live` is excluded from `deterministic_paths()`, so it never runs in CI and never turns red on a
machine with no account. Running it is an explicit act. That is the honest shape for a test whose subject is
the operator's own drive: PENDING is a real state, and it says so out loud with the exact steps to enable it
rather than passing vacuously and being mistaken for coverage.

## What it deliberately does NOT do

It never asserts a file NAME, a folder name or any content, and never prints one. This repository is public
and its test reports have leaked personal data before (110 of 186 voice reports carried the operator's name
and agenda). So every assertion here is about SHAPE and INVARIANTS — that entries are normalized, that a
folder is told from a file, that a breadcrumb walks upward — never about what the operator happens to own.

## To run it

    1. ⚙ → Conectores → Google Drive (or OneDrive): paste the client_id of your own OAuth app and connect,
       choosing the browsing permission.
    2. cd engine && ./.venv/bin/python -m pytest tests/connectors/unit/files/live_cloud_drive_roundtrip.py -v

    ZAELAR_LIVE_FILES_PROVIDER=onedrive picks the other one when both are connected.
"""
from __future__ import annotations

import os

import pytest

from connectors.files import oauth, providers, service

_NORMALIZED = {"id", "name", "kind", "mime", "size", "modified", "web_url", "provider"}


def _connected() -> str:
    """The provider to exercise, or '' — a browsable, connected one. A connected provider whose granted tier
    cannot list is NOT a candidate: it would «pass» by correctly returning nothing."""
    want = (os.getenv("ZAELAR_LIVE_FILES_PROVIDER") or "").strip().lower()
    for pid in ([want] if want else providers.ids()):
        p = providers.get(pid)
        if not p or not oauth.tokens_present(pid):
            continue
        if p.tier(oauth.granted_tier(pid)).browsable:
            return pid
    return ""


@pytest.fixture(scope="module")
def provider() -> str:
    pid = _connected()
    if not pid:
        pytest.skip(
            "PENDING — no cloud drive connected with a browsing permission. Connect one in "
            "⚙ → Conectores (paste your own OAuth app's client_id, choose the browsing tier) and run this "
            "file again. This is a real state, not a failure: the circuit is built and waiting for an account.")
    return pid


def test_the_token_refreshes_without_a_new_consent(provider):
    """The whole connector rests on this: an access token expires in an hour and the operator is not going to
    re-consent every hour. A refresh that silently drops the refresh_token breaks days later, far from here."""
    tok = oauth.access_token(provider)
    assert tok, "no usable access token — the refresh path failed"
    assert oauth.account(provider).get("refresh_token"), "the refresh token must survive a refresh"


def test_the_root_lists_and_every_entry_is_NORMALIZED(provider):
    out = service.list_folder(provider=provider)
    assert out["ok"], out.get("error")
    assert out.get("reason") == "", "a browsable tier must not report a reason"
    for e in out["entries"]:
        assert set(e) >= _NORMALIZED, sorted(set(_NORMALIZED) - set(e))
        assert e["kind"] in ("folder", "file")
        assert isinstance(e["name"], str) and e["name"], "an entry with no name is unusable on screen"
        assert e["size"] is None or isinstance(e["size"], int)
        assert e["provider"] == provider, "an entry must say which drive it came from"


def test_a_folder_opens_and_its_breadcrumb_walks_back_up(provider):
    """Skips rather than fails when the account has no folder at the root — «this drive is flat» is a fact
    about the operator's data, not a defect in ours."""
    root = service.list_folder(provider=provider)
    folders = [e for e in root["entries"] if e["kind"] == "folder"]
    if not folders:
        pytest.skip("no folder at the root of this drive — nothing to walk into")
    fid = folders[0]["id"]
    inner = service.list_folder(provider=provider, folder_id=fid)
    assert inner["ok"], inner.get("error")
    trail = service.breadcrumb(fid, provider=provider)["trail"]
    assert trail and trail[-1]["id"] == fid, "the trail must END at the folder it describes"
    assert all(c.get("name") for c in trail), "a nameless crumb is an unclickable gap"


def test_a_search_answers_with_normalized_entries(provider):
    """Searches for a single letter — the point is the SHAPE of the answer, not what the operator owns. Zero
    results is a legitimate outcome and is not asserted against."""
    out = service.search("a", provider=provider)
    assert out["ok"], out.get("error")
    for e in out["entries"]:
        assert set(e) >= _NORMALIZED
        assert e["kind"] in ("folder", "file")


def test_a_file_resolves_to_its_own_metadata(provider):
    root = service.list_folder(provider=provider)
    files = [e for e in root["entries"] if e["kind"] == "file"]
    if not files:
        pytest.skip("no file at the root of this drive")
    got = service.item(files[0]["id"], provider=provider)
    assert got["ok"], got.get("error")
    assert got["entry"]["id"] == files[0]["id"]
    assert "parents" in got["entry"], "the breadcrumb is built from this"


def test_the_widget_sees_the_same_drive_through_its_own_seam(provider):
    """The widget talks to `service`, so this closes the circuit end to end: connector → service → data-op →
    what the card and the prompt would show. Runs against a TEMPORARY workspace so the operator's own
    explorer state is never written by a test."""
    import importlib
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        old = os.environ.get("ZAELAR_WORKSPACE")
        os.environ["ZAELAR_WORKSPACE"] = tmp
        try:
            from nucleo import workspace
            from widgets import store as wstore
            importlib.reload(workspace)
            importlib.reload(wstore)
            from widgets.archivos import data as wdata
            importlib.reload(wdata)

            out = wdata.apply_action("set_provider", {"provider": provider})
            assert out["ok"], out
            view = wdata.view_data()
            assert view["connected"] and view["provider"] == provider
            assert view["needs_refresh"] is False, "a listing just fetched is not stale"
            digest = wdata.prompt_digest()
            assert digest and "sin ningún servicio" not in digest, (
                "with a live drive the brain must see the folder, not the disconnected notice")
        finally:
            if old is None:
                os.environ.pop("ZAELAR_WORKSPACE", None)
            else:
                os.environ["ZAELAR_WORKSPACE"] = old
            from nucleo import workspace
            from widgets import store as wstore
            importlib.reload(workspace)
            importlib.reload(wstore)
