"""A picture errand's site-scoped image search lands in the photo viewer, never in a sheet (2.503).

show-real-photo-of-a-new-car__us (2026-10-11): the one row the worker's search brought back («Ferrari Amalfi -
Ferrari.com», a page) went to the results table, 172 s after the last turn; the verified press photos never
reached the viewer. What an image search scoped to the official site returns FROM that site replaces the set on
screen, with the site as its source; an unscoped search or a lone match leaves his set alone, and nothing of a
picture errand goes to `results`.
"""
from __future__ import annotations

import types

import pytest

from nucleo import picture_errand, surfaces
from nucleo.workers import findings
from widgets.imagenes import data as img

ROWS = [
    {"title": "Amalfi front", "url": "https://www.ferrari.com/en-EN/auto/ferrari-amalfi",
     "image": "https://cdn.ferrari.com/cms/a1.jpg"},
    {"title": "Amalfi side", "url": "https://www.ferrari.com/en-EN/media-centre/articles/ferrari-amalfi",
     "image": "https://cdn.ferrari.com/cms/a2.jpg"},
    {"title": "Roma on a blog", "url": "https://carblog.example/roma", "image": "https://carblog.example/r.jpg"},
]
REC = types.SimpleNamespace(surface=surfaces.IMAGES, task_id="2", title="Ferrari Amalfi official photos", sheet="")


@pytest.fixture
def no_sheet(monkeypatch):
    pushed = []
    monkeypatch.setattr("widgets.results.intake.push", lambda rows, **k: pushed.append(rows) or len(rows))
    monkeypatch.setattr("memory.api.state", lambda: {"open_widgets": ["imagenes"]})
    return pushed


def test_the_official_pictures_replace_the_set(no_sheet):
    res = {"query": "Ferrari Amalfi site:ferrari.com", "candidates": ROWS, "results": []}
    assert findings.hand_search_rows(REC, res) == 0 and no_sheet == []
    shown = img.view_data()
    assert [i["url"] for i in shown["items"]] == ["https://cdn.ferrari.com/cms/a1.jpg",
                                                  "https://cdn.ferrari.com/cms/a2.jpg"]
    assert shown["source"] == "ferrari.com" and res["viewer"] == {"shown": 2, "site": "ferrari.com"}


def test_an_unscoped_search_leaves_his_set_alone(no_sheet):
    img.apply_action("show", {"items": [{"url": "https://x.example/old.jpg"}], "query": "old"})
    res = {"query": "Ferrari Amalfi photos", "candidates": ROWS, "results": [{"title": "t", "url": "u"}]}
    assert findings.hand_search_rows(REC, res) == 0 and no_sheet == [], "a picture errand writes no sheet"
    assert [i["url"] for i in img.view_data()["items"]] == ["https://x.example/old.jpg"]
    assert res["viewer"]["shown"] == 0 and "site:" in res["viewer"]["why"]


def test_a_lone_match_is_not_the_official_set(no_sheet):
    img.apply_action("show", {"items": [{"url": "https://x.example/old.jpg"}], "query": "old"})
    res = {"query": "Ferrari Amalfi site:ferrari.com", "candidates": ROWS[:1] + ROWS[2:]}
    findings.hand_search_rows(REC, res)
    assert [i["url"] for i in img.view_data()["items"]] == ["https://x.example/old.jpg"]
    assert res["viewer"]["shown"] == 0


def test_a_list_errand_still_fills_its_sheet(no_sheet):
    rec = types.SimpleNamespace(surface=surfaces.LIST, task_id="3", sheet="ab-1")
    findings.hand_search_rows(rec, {"query": "q", "results": [{"title": "Shop", "url": "https://s.example"}]})
    assert no_sheet and no_sheet[0][0]["title"] == "Shop"


def test_the_scope_is_the_site_and_its_subdomains():
    site, items = picture_errand.pictures_of_site("x site:www.ferrari.com", ROWS)
    assert site == "ferrari.com" and len(items) == 2 and all(i["site"] == "ferrari.com" for i in items)
