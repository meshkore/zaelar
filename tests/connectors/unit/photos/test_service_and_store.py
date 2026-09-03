"""V2-564 — the Google Photos connector: the picker's session lifecycle, the local index that makes
browsing possible at all (Google never re-serves "the whole library" — see `connectors/photos/providers.py`),
and the past-oriented date parser that is deliberately NOT `nucleo/scheduler.py::parse_when` (that one is
future-only, built for reminders).

What is guarded here is the reasoning, not "the HTTP call works" — that needs a real Google account and lives
behind a `live: True` node. The traps this connector has to avoid:

  · A session with nothing picked yet is NOT an error (T1 from the workflow doc) — `poll_session` on a
    pending session that hasn't finished must say so without raising.
  · A date phrase in Spanish carries accents ("año"), and the regex matching happens on an ACCENT-STRIPPED
    copy of the text. Removing the matched phrase from the ORIGINAL (accented) string by string substitution
    silently fails — this was caught and fixed while writing these tests, not before.
  · A thumbnail is a signed, time-limited Google URL; only the local cached JPEG path survives past that.
"""
from __future__ import annotations

import time

import pytest

from connectors.photos import providers, service, store


# ── providers / oauth registry ────────────────────────────────────────────────────────────────────────────
def test_google_photos_has_exactly_one_tier_and_it_does_not_browse():
    p = providers.get("google-photos")
    assert len(p.tiers) == 1
    assert p.tiers[0].browsable is False, (
        "the Picker is the ONLY surface Google offers to third-party apps since March 2025 — there is no "
        "tier that browses the whole library, unlike Drive's drive.readonly")


def test_public_list_carries_no_endpoints_or_credentials():
    import json
    rows = {r["id"]: r for r in providers.public_list()}
    blob = json.dumps(rows)
    assert "googleapis.com" not in blob
    assert set(rows) == {"google-photos"}


# ── the local index (store.py) — isolated widgets store ─────────────────────────────────────────────────────
@pytest.fixture
def idx(tmp_path, monkeypatch):
    """ISOLATED widget data dir — never the operator's real photo index."""
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    return store


def _item(iid, taken_at="", filename="p.jpg"):
    return {"id": iid, "filename": filename, "taken_at": taken_at, "mime": "image/jpeg",
            "width": 100, "height": 100, "provider": "google-photos"}


def test_upsert_is_idempotent_by_id(idx):
    bid = idx.add_batch(["1"], "google-photos")
    n1 = idx.upsert_items([_item("1", "2024-01-01")], bid)
    n2 = idx.upsert_items([_item("1", "2024-01-01")], bid)
    assert n1 == 1 and n2 == 0, "re-importing the same item must not duplicate it"
    assert idx.item_count() == 1


def test_items_sort_newest_first_and_undated_last(idx):
    bid = idx.add_batch(["a", "b", "c"], "google-photos")
    idx.upsert_items([_item("a", "2020-01-01"), _item("b", "2024-06-15"), _item("c", "")], bid)
    ordered = [it["id"] for it in idx.all_items()]
    assert ordered == ["b", "a", "c"], "newest taken_at first, undated sorts LAST rather than to a wrong end"


def test_years_summary_groups_and_counts():
    d = {"items": {
        "1": _item("1", "2024-03-01"), "2": _item("2", "2024-07-01"), "3": _item("3", "2022-01-01"),
    }}
    ys = {row["year"]: row["count"] for row in store.years_summary(d)}
    assert ys == {"2024": 2, "2022": 1}


def test_page_bounds_size_and_reports_has_more():
    d = {"items": {str(i): _item(str(i), "2024-01-01") for i in range(10)}}
    res = store.page(0, 4, d)
    assert len(res["items"]) == 4 and res["has_more"] is True and res["total"] == 10
    res2 = store.page(res["next_offset"], 4, d)
    assert len(res2["items"]) == 4


def test_label_batch_and_filter_by_label(idx):
    bid = idx.add_batch(["m1"], "google-photos", label="")
    idx.upsert_items([_item("m1", "2024-05-01", "camel.jpg")], bid)
    idx.label_batch(bid, "Marruecos")
    matches = idx.filter_items(label_substr="marruecos")
    assert [m["id"] for m in matches] == ["m1"], "the label filter is case-insensitive"
    assert idx.filter_items(label_substr="nope") == []


def test_filter_by_date_range_excludes_undated_when_a_lower_bound_is_given():
    d = {"items": {
        "in": _item("in", "2024-06-15"), "out": _item("out", "2023-01-01"), "nodate": _item("nodate", ""),
    }}
    out = store.filter_items("2024-01-01", "2024-12-31", d=d)
    assert [it["id"] for it in out] == ["in"], (
        "a date-bounded search skips undated items rather than guessing they might qualify")


def test_thumb_path_is_confined_to_the_thumbs_dir(idx):
    p = idx.thumb_path("weird/../id")
    assert p.parent.name == "thumbs" and ".." not in str(p.name)


# ── the picker session round trip (service.py) — T1: pending is not an error ────────────────────────────────
@pytest.fixture
def wired(monkeypatch, tmp_path):
    """Isolated store + a fake token so `service` never needs real OAuth/Google."""
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(service._oauth, "configured", lambda pid: True)
    monkeypatch.setattr(service._oauth, "access_token", lambda pid: "tok")
    monkeypatch.setattr(service._oauth, "status", lambda: [
        {"id": "google-photos", "label": "Google Photos", "app_configured": True, "connected": True,
         "tier": "picked", "tier_label": "x", "browsable": False, "note": ""}])
    return service


def test_start_session_without_a_registered_app_asks_for_one(monkeypatch, tmp_path):
    from widgets import store as wstore
    monkeypatch.setattr(wstore, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(service._oauth, "configured", lambda pid: False)
    out = service.start_session()
    assert out["ok"] is False and out["needs_app"] is True


def test_a_pending_session_is_not_an_error(wired, monkeypatch):
    monkeypatch.setattr(service._gp, "create_session",
                        lambda tok: {"id": "s1", "picker_uri": "https://photos.google.com/picker/s1",
                                     "poll_interval_s": 5, "media_items_set": False})
    res = wired.start_session()
    assert res["ok"] and res["picker_uri"].startswith("https://")

    monkeypatch.setattr(service._gp, "get_session",
                        lambda tok, sid: {"id": sid, "picker_uri": "", "media_items_set": False,
                                          "poll_interval_s": 5})
    poll = wired.poll_session()
    assert poll["ok"] is True and poll["ready"] is False and poll["pending"] is True, (
        "nothing has been picked yet — that is a legitimate state, not a failure")


def test_a_finished_session_imports_and_downloads_thumbnails(wired, monkeypatch):
    monkeypatch.setattr(service._gp, "create_session",
                        lambda tok: {"id": "s1", "picker_uri": "u", "poll_interval_s": 5,
                                     "media_items_set": False})
    wired.start_session()
    monkeypatch.setattr(service._gp, "get_session",
                        lambda tok, sid: {"id": sid, "picker_uri": "", "media_items_set": True,
                                          "poll_interval_s": 5})
    monkeypatch.setattr(service._gp, "list_media_items", lambda tok, sid, page_token="": {
        "items": [{"id": "m1", "createTime": "2024-08-01T10:00:00Z",
                   "mediaFile": {"filename": "camel.jpg", "mimeType": "image/jpeg",
                                 "baseUrl": "https://example.test/base",
                                 "mediaFileMetadata": {"width": 800, "height": 600}}}],
        "next": ""})
    monkeypatch.setattr(service._gp, "download_bytes", lambda url: b"\xff\xd8fake")
    monkeypatch.setattr(service._gp, "delete_session", lambda tok, sid: None)

    res = wired.poll_session()
    assert res["ready"] is True and res["imported"] == 1
    page = wired.list_page()
    assert page["items"][0]["filename"] == "camel.jpg"
    assert page["items"][0]["thumb"], "an imported item with a downloaded thumbnail must expose a /thumb URL"


def test_a_client_that_blows_up_degrades_instead_of_raising(wired, monkeypatch):
    def boom(tok):
        raise RuntimeError("photos picker 503")
    monkeypatch.setattr(service._gp, "create_session", boom)
    out = wired.start_session()
    assert out["ok"] is False and "503" in out["error"]


# ── the past-oriented date parser — deliberately NOT nucleo.scheduler.parse_when ─────────────────────────────
_NOW = time.mktime((2026, 9, 3, 12, 0, 0, 0, 0, -1))   # a fixed "today" so "last year"/"this June" are stable


def test_last_year_with_a_label_strips_the_date_phrase_even_with_the_accent():
    date_from, date_to, label = service._parse_date_hint("fotos de Marruecos el año pasado", _NOW)
    assert (date_from, date_to) == ("2025-01-01", "2025-12-31")
    assert label == "Marruecos", (
        "removing the matched phrase by re.sub(consumed_stripped_of_accents, raw) silently fails on 'año' — "
        "this must remove by INDEX SPAN, not by re-searching the original text for the accent-free match")


def test_this_year_in_english():
    date_from, date_to, label = service._parse_date_hint("photos from this year", _NOW)
    assert (date_from, date_to) == ("2026-01-01", "2026-12-31")


def test_years_ago():
    date_from, date_to, _ = service._parse_date_hint("hace 2 años", _NOW)
    assert (date_from, date_to) == ("2024-01-01", "2024-12-31")


def test_a_bare_month_resolves_to_a_past_or_current_occurrence_never_the_future():
    # "now" is September 2026: June (month 6) has already happened this year.
    date_from, date_to, residue = service._parse_date_hint("en junio", _NOW)
    assert (date_from, date_to) == ("2026-06-01", "2026-06-30")
    assert residue == "", "a pure date phrase leaves nothing for the label filter to (wrongly) match against"

    # December (month 12) has NOT happened yet this year -> must resolve to LAST december, not a future one.
    date_from, date_to, _ = service._parse_date_hint("en diciembre", _NOW)
    assert date_from.startswith("2025-12")


def test_a_bare_year_is_a_whole_year_range():
    date_from, date_to, _ = service._parse_date_hint("2019", _NOW)
    assert (date_from, date_to) == ("2019-01-01", "2019-12-31")


def test_no_date_shape_makes_the_whole_text_the_label():
    date_from, date_to, label = service._parse_date_hint("la boda de mi hermana", _NOW)
    assert date_from == "" and date_to == ""
    assert label == "la boda de mi hermana"
