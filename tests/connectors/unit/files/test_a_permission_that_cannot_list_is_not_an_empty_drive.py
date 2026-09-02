"""V2-557 — the cloud-file connector: scope tiers, the PKCE flow, and the two failures that look identical.

What is guarded here is not «the HTTP call works» — that needs a real account and lives in the live node. It
is the reasoning around it, which is where this connector can be wrong while answering 200:

  · A permission that CANNOT LIST answers with an empty array, exactly like an empty folder. Collapsing those
    two is how «your Drive is empty» gets shown to somebody whose Drive is full, and how the defect gets
    diagnosed as a broken connector instead of a narrow scope.
  · A single quote in a file name ends Drive's query string early and turns the rest of the operator's
    sentence into syntax. «Pepe's contract» is a legal file name and a 400 nobody can read.
  · A refresh response does not always return the refresh_token; dropping it disconnects the operator on the
    second refresh of the day, hours after the change that caused it.
"""
from __future__ import annotations

import json
import time

import pytest

from connectors.files import gdrive, onedrive, providers, service
from connectors.files import oauth as fo


# ── the registry: tiers are the design, so they are asserted like one ───────────────────────────────────────
def test_google_ships_both_tiers_and_only_one_of_them_can_browse():
    p = providers.get("gdrive")
    ids = {t.id: t for t in p.tiers}
    assert set(ids) == {"browse", "picked"}
    assert ids["browse"].browsable is True
    assert ids["picked"].browsable is False, (
        "drive.file only sees what the app created or the user picked — if this ever reads True, the widget "
        "will show an empty root as if it were the truth")


def test_onedrive_has_one_tier_and_it_browses():
    p = providers.get("onedrive")
    assert len(p.tiers) == 1 and p.tiers[0].browsable is True
    assert "offline_access" in p.tiers[0].scopes, "without it there is no refresh token at all"


def test_an_unknown_tier_falls_back_instead_of_raising():
    """A stale config naming a tier that no longer exists must not take the connector down."""
    p = providers.get("gdrive")
    assert p.tier("does-not-exist").id == p.default_tier
    assert p.tier("").id == p.default_tier


def test_the_public_list_carries_the_tiers_and_no_endpoints():
    rows = {r["id"]: r for r in providers.public_list()}
    assert set(rows) == {"gdrive", "onedrive"}
    blob = json.dumps(rows)
    assert "googleapis.com" not in blob and "login.microsoftonline" not in blob, (
        "the connect form gets labels and notes, never endpoints")
    assert rows["gdrive"]["tiers"] and rows["gdrive"]["default_tier"] == "browse"


# ── OAuth: the consent URL, the state, and the token store ─────────────────────────────────────────────────
@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Point the credential store at a tmp file. A test NEVER reads or writes the operator's real tokens."""
    monkeypatch.setattr(fo, "STORE", tmp_path / "files_oauth.json")
    monkeypatch.setattr(fo, "client_id", lambda pid: "cid-123")
    monkeypatch.setattr(fo, "client_secret", lambda pid: "")
    return tmp_path / "files_oauth.json"


def test_the_consent_url_carries_pkce_the_chosen_scopes_and_googles_offline_params(store):
    res = fo.authorize_url("gdrive", "picked")
    assert res["ok"] and res["tier"] == "picked"
    url = res["url"]
    assert "code_challenge_method=S256" in url and "code_challenge=" in url
    assert "drive.file" in url and "drive.readonly" not in url, "the CHOSEN tier's scopes, not the default"
    # Without these two Google never returns a refresh token, and the connector dies at the first expiry.
    assert "access_type=offline" in url and "prompt=consent" in url


def test_the_chosen_tier_is_stashed_because_the_callback_carries_only_code_and_state(store):
    res = fo.authorize_url("gdrive", "picked")
    state = res["url"].split("state=")[1].split("&")[0]
    pend = json.loads(store.read_text())["pending"][state]
    assert pend["tier"] == "picked" and pend["provider"] == "gdrive" and pend["verifier"]


def test_an_unknown_state_is_refused(store):
    assert fo.exchange_code("code", "never-issued")["ok"] is False


def test_an_abandoned_consent_is_pruned(store, monkeypatch):
    fo.authorize_url("gdrive")
    data = json.loads(store.read_text())
    (k,) = list(data["pending"])
    data["pending"][k]["ts"] = int(time.time()) - (fo._PENDING_TTL + 60)
    store.write_text(json.dumps(data))
    fo.authorize_url("gdrive")                       # any new flow prunes
    assert k not in json.loads(store.read_text())["pending"]


def test_a_refresh_without_a_new_refresh_token_keeps_the_old_one(store):
    fo._store_tokens("gdrive", "browse", {"access_token": "a1", "refresh_token": "R", "expires_in": 3600})
    fo._store_tokens("gdrive", "browse", {"access_token": "a2", "expires_in": 3600})
    assert fo.account("gdrive")["refresh_token"] == "R", (
        "providers omit refresh_token on refresh; dropping it disconnects the operator later, silently")
    assert fo.account("gdrive")["access_token"] == "a2"


def test_the_granted_tier_is_remembered_so_the_widget_can_explain_itself(store):
    fo._store_tokens("gdrive", "picked", {"access_token": "a", "refresh_token": "r", "expires_in": 10})
    assert fo.granted_tier("gdrive") == "picked"
    row = {r["id"]: r for r in fo.status()}["gdrive"]
    assert row["connected"] is True and row["browsable"] is False


def test_forget_removes_the_account_and_leaves_the_others(store):
    fo._store_tokens("gdrive", "browse", {"access_token": "a", "refresh_token": "r", "expires_in": 10})
    fo._store_tokens("onedrive", "browse", {"access_token": "b", "refresh_token": "s", "expires_in": 10})
    fo.forget("gdrive")
    assert not fo.tokens_present("gdrive") and fo.tokens_present("onedrive")


# ── the service: the distinction this whole layer exists for ───────────────────────────────────────────────
@pytest.fixture()
def connected(monkeypatch):
    """A connected gdrive whose granted tier the test chooses."""
    def _go(tier="browse"):
        monkeypatch.setattr(service._oauth, "configured", lambda pid: True)
        monkeypatch.setattr(service._oauth, "access_token", lambda pid: "tok")
        monkeypatch.setattr(service._oauth, "granted_tier", lambda pid: tier)
        monkeypatch.setattr(service._oauth, "status", lambda: [
            {"id": "gdrive", "label": "Google Drive", "app_configured": True, "connected": True,
             "tier": tier, "tier_label": "x", "browsable": tier == "browse", "note": ""}])
    return _go


def test_a_narrow_permission_answers_ok_WITH_A_REASON_never_an_empty_listing(connected):
    connected("picked")
    out = service.list_folder()
    assert out["ok"] is True and out["entries"] == []
    assert out["reason"], (
        "ok+0 entries+no reason is indistinguishable from an empty folder — that is the whole defect")
    assert "permiso" in out["reason"].lower()


def test_a_browsable_permission_carries_no_reason(connected, monkeypatch):
    connected("browse")
    monkeypatch.setattr(gdrive, "list_folder",
                        lambda *a, **k: {"entries": [{"id": "1", "name": "x"}], "next": ""})
    out = service.list_folder()
    assert out["ok"] and out["entries"] and out["reason"] == "", (
        "a reason that shows up on the healthy path is noise, and noise stops being read")


def test_a_client_that_blows_up_degrades_instead_of_raising(connected, monkeypatch):
    connected("browse")
    def boom(*a, **k):
        raise RuntimeError("drive 503: upstream")
    monkeypatch.setattr(gdrive, "list_folder", boom)
    out = service.list_folder()
    assert out["ok"] is False and "503" in out["error"], "a provider outage may not take a voice turn with it"


def test_not_connected_and_not_configured_say_DIFFERENT_things(monkeypatch):
    monkeypatch.setattr(service._oauth, "status", lambda: [
        {"id": "gdrive", "connected": False, "label": "Google Drive", "app_configured": False}])
    assert "conectado" in service.list_folder()["error"]
    monkeypatch.setattr(service._oauth, "status", lambda: [
        {"id": "gdrive", "connected": True, "label": "Google Drive", "app_configured": False}])
    monkeypatch.setattr(service._oauth, "configured", lambda pid: False)
    assert "OAuth" in service.list_folder(provider="gdrive")["error"]


def test_an_empty_search_is_refused_rather_than_sent(connected):
    connected("browse")
    out = service.search("   ")
    assert out["ok"] is False, "every provider answers a blank search with the whole drive, which is not a search"


def test_a_preference_pointing_at_a_disconnected_provider_falls_back(connected):
    connected("browse")            # only gdrive is connected
    assert service.active_provider("onedrive") == "gdrive", (
        "a stale preference must not silently produce «empty drive»")


def test_the_breadcrumb_is_bounded_against_a_cycle(connected, monkeypatch):
    connected("browse")
    # A parent chain that points at itself: without the bound this hangs a voice turn.
    monkeypatch.setattr(gdrive, "item", lambda t, b, fid: {"id": fid, "name": "loop", "parents": [fid]})
    out = service.breadcrumb("f1")
    assert out["ok"] and len(out["trail"]) == 1


# ── the two clients: the provider facts that are easy to assume away ───────────────────────────────────────
def test_drive_escapes_the_quote_that_would_end_its_query_string():
    assert gdrive._escape("Pepe's contract") == "Pepe\\'s contract"
    assert gdrive._escape("back\\slash") == "back\\\\slash"


def test_drive_reads_a_folder_from_its_MIME_and_leaves_a_native_doc_without_a_size():
    folder = gdrive._entry({"id": "1", "name": "F", "mimeType": gdrive.FOLDER_MIME})
    doc = gdrive._entry({"id": "2", "name": "D", "mimeType": "application/vnd.google-apps.document"})
    real = gdrive._entry({"id": "3", "name": "R", "mimeType": "application/pdf", "size": "1024"})
    assert folder["kind"] == "folder" and doc["kind"] == "file"
    assert doc["size"] is None, "«0 B» next to every Google Doc somebody owns is a statement, and it is false"
    assert real["size"] == 1024


def test_a_native_google_doc_EXPORTS_and_everything_else_downloads():
    base = "https://www.googleapis.com/drive/v3"
    assert "/export?" in gdrive.download_url(base, "1", "application/vnd.google-apps.document")
    assert "alt=media" in gdrive.download_url(base, "1", "application/pdf")


def test_graph_reads_a_folder_from_its_FACET_not_from_a_mime():
    folder = onedrive._entry({"id": "1", "name": "F", "folder": {"childCount": 2}})
    f = onedrive._entry({"id": "2", "name": "x.pdf", "size": 9, "file": {"mimeType": "application/pdf"}})
    assert folder["kind"] == "folder" and folder["size"] is None
    assert f["kind"] == "file" and f["size"] == 9 and f["mime"] == "application/pdf"


def test_graph_addresses_the_root_by_PATH_and_anything_else_by_id():
    assert onedrive._children_path("") == "/me/drive/root/children"
    assert onedrive._children_path("root") == "/me/drive/root/children"
    assert onedrive._children_path("01ABC") == "/me/drive/items/01ABC/children"


def test_both_clients_emit_the_SAME_normalized_keys():
    """The seam is only real if the two clients are interchangeable above it."""
    g = set(gdrive._entry({"id": "1", "name": "n", "mimeType": "text/plain"}))
    o = set(onedrive._entry({"id": "1", "name": "n", "file": {"mimeType": "text/plain"}}))
    assert g == o == {"id", "name", "kind", "mime", "size", "modified", "web_url", "provider"}
