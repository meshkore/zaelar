"""The ACCOUNT layer of the video widget (V2-597): intent travels, credentials never do.

The wizard/status screens are driven by declared actions — `open_connectors` (the voice door),
`connect_account` (returns the consent URL for an app registered ONCE in the settings panel),
`disconnect_account`, `suggest` and the card's own `sync_platforms`. The boundary under test is V2-520's:
no declared payload may carry a credential, and the suggestions band honors the operator's blocked-channels
filter at the same door as every other name search.
"""
import json
import pathlib
import time

import pytest

from widgets import store
from widgets.youtube import data as yt


@pytest.fixture(autouse=True)
def _account_layer_enabled(monkeypatch):
    """V2-603 F2 gated the three account doors behind «is there an OAuth client at all?», and today there is
    none — so every case in this file would decline before reaching the mechanism it exists to test.

    The MECHANISM is not what was deactivated: it is built, and it has to keep working for the day the client
    id lands (that is the whole point of a DERIVED gate). So this file measures it with the layer forced on,
    and the gate itself is measured in
    `tests/connectors/unit/video/test_connecting_an_account_is_one_step_and_failures_reach_the_operator.py`
    — one file per question, neither able to hide the other's regression."""
    monkeypatch.setattr(yt, "_accounts_enabled", lambda: True)

_MANIFEST = pathlib.Path(yt.__file__).parent / "manifest.json"


class _FakeSvc:
    """Stands in for connectors.video.service — same keys, no network."""

    def __init__(self):
        self.rows = [{"id": "youtube", "label": "YouTube", "app_configured": True,
                      "connected": True, "note": ""}]
        self.sugg = {"ok": True, "provider": "youtube", "channels": 3, "fetched_at": int(time.time()),
                     "items": [
                         {"videoId": "AAAAAAAAAA1", "title": "Coches del futuro", "channel": "Lucid AI Cars",
                          "published": "2026-09-01", "url": "https://youtu.be/AAAAAAAAAA1"},
                         {"videoId": "BBBBBBBBBB2", "title": "Ferrari F40 real", "channel": "Motor Clasico",
                          "published": "2026-09-02", "url": "https://youtu.be/BBBBBBBBBB2"},
                     ]}

    def status(self):
        return {"ok": True, "providers": self.rows}

    def suggestions(self, provider="youtube", limit=24):
        return self.sugg

    def connect_url(self, provider, tier=""):
        return {"ok": True, "url": "https://accounts.google.com/consent?x=1", "tier": "readonly"}

    def disconnect(self, provider):
        self.rows[0]["connected"] = False
        return {"ok": True, "provider": provider}


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    svc = _FakeSvc()
    monkeypatch.setattr(yt, "_svc", lambda: svc)
    return svc


def _manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


# ── the manifest boundary ─────────────────────────────────────────────────────────────────────────────────
def test_the_account_actions_are_declared_and_the_view_ones_say_so():
    acts = _manifest()["actions"]
    for name in ("sync_platforms", "open_connectors", "connect_account", "disconnect_account", "suggest"):
        assert name in acts, name
    assert acts["open_connectors"].get("view") is True
    assert acts["suggest"].get("view") is True
    assert acts["disconnect_account"].get("confirm") is True


def test_no_declared_payload_carries_a_credential():
    # V2-520: voice carries INTENT, never a credential. The scan covers what an action ACCEPTS (its payload
    # keys and their docs) — prose in a desc may honestly say "forgets its tokens" without accepting one.
    payloads = json.dumps({k: v.get("payload") or {} for k, v in _manifest()["actions"].items()}).lower()
    for bad in ("client_secret", "client_id", "password", "api_key", "token", "secret"):
        assert bad not in payloads, bad


def test_the_routing_line_still_fits_its_budget():
    from widgets import brief
    assert len(_manifest()["whenToUse"]) <= brief._PURPOSE_CAP


# ── the data half ─────────────────────────────────────────────────────────────────────────────────────────
def test_open_connectors_writes_a_timestamped_focus_and_falls_back_to_youtube(sandbox):
    r = yt.apply_action("open_connectors", {"platform": "vimeo"})
    assert r["ok"] and r["platform"] == "youtube"        # unknown platform → the one that exists
    db = yt._load()
    assert db["connect_focus"]["platform"] == "youtube"
    assert int(db["connect_focus"]["ts"]) > 0
    assert db["platforms"] and db["platforms"][0]["id"] == "youtube"


def test_sync_platforms_caches_rows_and_view_data_computes_staleness(sandbox):
    r = yt.apply_action("sync_platforms", {})
    assert r["ok"] and r["platforms"][0]["connected"] is True
    v = yt.view_data()
    assert v["platforms"][0]["id"] == "youtube"
    assert v["platforms_stale"] is False                 # just synced
    db = yt._load()
    db["platforms_at"] = int(time.time()) - 3600
    store.save(yt.WID, db)
    assert yt.view_data()["platforms_stale"] is True     # computed from age, never stored


def test_connect_account_returns_the_url_and_nothing_stores_a_credential(sandbox):
    r = yt.apply_action("connect_account", {"platform": "youtube", "client_secret": "sneaky"})
    assert r["ok"] and r["url"].startswith("https://accounts.google.com/")
    # The stray credential in the payload is IGNORED — nothing in the widget's store may hold it.
    raw = json.dumps(yt._load())
    assert "sneaky" not in raw


def test_suggest_fills_the_band_filtered_by_blocked_channels_and_says_the_count(sandbox):
    yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    r = yt.apply_action("suggest", {})
    assert r["ok"] and r["n"] == 1 and r["blocked_out"] == 1 and r["channels"] == 3
    db = yt._load()
    assert [it["title"] for it in db["suggested"]] == ["Ferrari F40 real"]
    assert db["suggested_at"] > 0 and db["suggesting"] is False


def test_suggest_passes_a_legitimate_emptiness_through_as_ok_plus_reason(sandbox):
    svc = sandbox
    svc.sugg = {"ok": True, "provider": "youtube", "items": [], "channels": 0,
                "reason": "la cuenta no tiene suscripciones — no hay de dónde sacar sugerencias"}
    r = yt.apply_action("suggest", {})
    assert r["ok"] and r["n"] == 0 and "suscripciones" in r["reason"]


def test_a_failed_suggest_speaks_and_clears_the_busy_state(sandbox):
    svc = sandbox
    svc.sugg = {"ok": False, "error": "la sesión con YouTube caducó — reconecta la cuenta"}
    r = yt.apply_action("suggest", {})
    assert r["ok"] is False and "caducó" in r["error"]
    assert yt._load()["suggesting"] is False             # the visible state never sticks on failure


def test_block_channel_sweeps_the_suggestions_band_too(sandbox):
    yt.apply_action("suggest", {})
    assert len(yt._load()["suggested"]) == 2
    r = yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    assert r["ok"] and r["removed_from_list"] == 1
    assert [it["channel"] for it in yt._load()["suggested"]] == ["Motor Clasico"]


def test_disconnect_account_empties_the_band_a_disconnected_account_no_longer_backs(sandbox):
    yt.apply_action("suggest", {})
    assert yt._load()["suggested"]
    r = yt.apply_action("disconnect_account", {"platform": "youtube"})
    assert r["ok"]
    db = yt._load()
    assert db["suggested"] == [] and db["suggested_at"] == 0
    assert db["platforms"][0]["connected"] is False      # the cache re-synced on the way out


def test_a_missing_connector_package_degrades_to_words_never_a_traceback(sandbox, monkeypatch):
    monkeypatch.setattr(yt, "_svc", lambda: None)
    for action in ("connect_account", "disconnect_account", "suggest"):
        r = yt.apply_action(action, {})
        assert r["ok"] is False and "conector" in r["error"]
