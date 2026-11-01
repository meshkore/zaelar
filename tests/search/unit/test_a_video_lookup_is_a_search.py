"""A video — or a track to play — is found through the search service's one door (V2-833 F1).

The class: the music player's in-page resolver and the video card each scraped YouTube with a private copy (other
headers, another parser), with no second source and no outcome. On a hosted engine the music copy came back empty ten
times while the card's copy had worked on the same Machine two days before. Now both ask `search.video.find_videos`:
the results page, then the same page in the warm Chromium; every call reports what it got.
"""
from __future__ import annotations

import ast
import io
import urllib.request
from pathlib import Path

import pytest

from search import video

ENGINE = Path(__file__).resolve().parents[3]
_BLOCK = '"videoId":"{id}","thumbnail":{{}},"title":{{"runs":[{{"text":"{t}"}}]}},"ownerText":{{"runs":[{{"text":"Bizarrap"}}]}}'
PAGE = "<script>" + ",".join(_BLOCK.format(id=i, t=t) for i, t in (
    ("CocEMWdc7Ck", "SHAKIRA || BZRP Music Sessions #53/66"), ("aaaaaaaaaa1", "Another one"))) + "</script>"


@pytest.fixture
def world(monkeypatch):
    from search import browser
    from voice import observer
    seen = {"events": [], "page": PAGE, "browser": None}

    def _open(req, timeout=0):
        if seen["page"] is None:
            raise TimeoutError("timed out")
        return io.BytesIO(seen["page"].encode())

    def _chromium(url):
        if seen["browser"] is None:
            raise RuntimeError("browser_search: loop del server no enlazado todavía")
        return seen["browser"]
    monkeypatch.setattr(urllib.request, "urlopen", _open)
    monkeypatch.setattr(browser, "page_html_sync", _chromium)
    monkeypatch.setattr(observer, "emit", lambda kind, label, **k: seen["events"].append((kind, k.get("extra") or {})))
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    return seen


def _outcomes(seen) -> list[tuple[str, str]]:
    return [(e["provider"], e["reason"]) for k, e in seen["events"] if k == "provider"]


def test_the_song_and_the_video_ask_the_same_door(world):
    from connectors.music import youtube_resolve
    from widgets.youtube import data as yt
    assert youtube_resolve._resolve("Shakira Bizarrap Music Sessions 53")[0] == "CocEMWdc7Ck"
    assert yt._search_many("Shakira Bizarrap Music Sessions 53", 2)[0]["videoId"] == "CocEMWdc7Ck"
    assert {p for p, _ in _outcomes(world)} == {"youtube"}


@pytest.mark.parametrize("page", [None, "<html>before you continue to YouTube</html>"], ids=["unreachable", "no-videos"])
def test_when_the_page_gives_nothing_the_chromium_is_asked(world, page):
    world["page"], world["browser"] = page, PAGE
    hits = video.find_videos("cierre Cárpatos hoy", 3)
    assert [h["videoId"] for h in hits][:1] == ["CocEMWdc7Ck"]
    assert _outcomes(world) == [("youtube", "unreachable" if page is None else "empty"), ("youtube_browser", "found")]


def test_with_every_source_down_the_answer_is_empty_and_says_why(world):
    world["page"] = None
    assert video.find_videos("anything at all", 3) == []
    assert _outcomes(world) == [("youtube", "unreachable"), ("youtube_browser", "unreachable")]


def test_no_private_youtube_scrape_is_left():
    for rel in ("widgets/youtube/data.py", "connectors/music/youtube_resolve.py"):
        tree = ast.parse((ENGINE / rel).read_text(encoding="utf-8"))
        assert not [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "urlopen"], rel


def test_both_sources_are_declared_providers_with_a_probe():
    from search.providers import PROVIDERS
    assert PROVIDERS["youtube"].kind == PROVIDERS["youtube_browser"].kind == "video"
    src = (ENGINE / "search/health.py").read_text(encoding="utf-8")
    assert 'name == "youtube"' in src and 'name == "youtube_browser"' in src
