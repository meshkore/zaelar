"""A pasted YouTube link is PARSED, never read as text (node 4.236).

Live on the operator's engine (2026-09-29), two links pasted into the chat:
- `watch?v=QLYIhB7h-Q0` loaded and played, and the card's title was the URL itself — the link names the
  video and nobody asked YouTube what it is called (`add` already did, through oembed; `load` did not).
- `results?search_query=Liverpool+Atletico+…` reached `search` with the WHOLE sentence as the query — the
  prose, the URL, the `+` signs — and the scraper answered a question nobody asked. A results link IS the
  query, already written: it is decoded and searched as such, from `search` and from `load` alike.
"""
import io
import urllib.request

import pytest

from widgets import store
from widgets.youtube import data as yt

_RESULTS_HTML = (
    '{"videoRenderer":{"videoId":"AAAAAAAAAA1","title":{"runs":[{"text":"Liverpool 2-3 Atletico, 11 March 2020"}]},'
    '"ownerText":{"runs":[{"text":"UEFA"}]}}}'
)
_URL = ("https://www.youtube.com/results?search_query=Liverpool+Atletico+Madrid+11+marzo+2020"
        "+Michael+Robinson+Carlos+Martinez")
_QUERY = "Liverpool Atletico Madrid 11 marzo 2020 Michael Robinson Carlos Martinez"


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    fetched: list[str] = []

    def _urlopen(req, timeout=6):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        fetched.append(url)
        if "oembed" in url:
            return io.BytesIO(b'{"title": "Liverpool v Atletico - the night Anfield fell silent", "author_name": "UEFA"}')
        return io.BytesIO(_RESULTS_HTML.encode("utf-8"))
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen)
    return fetched


def test_a_results_link_is_decoded_into_its_query():
    assert yt._results_query("open this youtube search: " + _URL) == _QUERY
    assert yt._results_query("https://www.youtube.com/results?search_query=paella%20de%20marisco&sp=EgIQAQ%253D%253D") == "paella de marisco"
    assert yt._results_query("videos de paella") == ""
    assert yt._results_query("https://www.youtube.com/watch?v=QLYIhB7h-Q0") == ""


def test_the_search_action_searches_the_decoded_query_not_the_sentence(sandbox):
    r = yt.apply_action("search", {"query": "open this youtube search: " + _URL})
    assert r["ok"] and r["count"] == 1
    d = yt.view_data()
    assert d["search_query"] == _QUERY, "the band is named by the query he pasted, not by the sentence"
    assert all("results?search_query=open" not in u for u in sandbox), "the scraper asked YouTube the decoded question"
    assert "Liverpool+Atletico+Madrid+11+marzo+2020+Michael+Robinson+Carlos+Martinez" in sandbox[0]


def test_a_results_link_given_to_load_is_a_search_never_a_guess(sandbox):
    r = yt.apply_action("load", {"url": "put on this: " + _URL})
    assert r["ok"] and r["count"] == 1 and r["query"] == _QUERY
    d = yt.view_data()
    assert d["videoId"] == "", "a results link chooses nothing: he chooses from the band"
    assert [x["videoId"] for x in d["search_results"]] == ["AAAAAAAAAA1"]


def test_a_bare_watch_link_gets_its_title_from_youtube(sandbox):
    r = yt.apply_action("load", {"url": "https://www.youtube.com/watch?v=QLYIhB7h-Q0"})
    assert r["ok"]
    d = yt.view_data()
    assert d["videoId"] == "QLYIhB7h-Q0"
    assert d["title"] == "Liverpool v Atletico - the night Anfield fell silent" and d["channel"] == "UEFA"
    assert any("oembed" in u for u in sandbox)


def test_a_watch_link_with_the_network_down_still_plays_under_its_url(sandbox, monkeypatch):
    def _down(req, timeout=6):
        raise OSError("offline")
    monkeypatch.setattr(urllib.request, "urlopen", _down)
    r = yt.apply_action("load", {"url": "https://www.youtube.com/watch?v=QLYIhB7h-Q0"})
    assert r["ok"] and yt.view_data()["title"] == "https://www.youtube.com/watch?v=QLYIhB7h-Q0"


def test_a_given_title_is_not_second_guessed(sandbox):
    yt.apply_action("load", {"url": "https://www.youtube.com/watch?v=QLYIhB7h-Q0", "title": "Sonando"})
    assert yt.view_data()["title"] == "Sonando" and not any("oembed" in u for u in sandbox)
