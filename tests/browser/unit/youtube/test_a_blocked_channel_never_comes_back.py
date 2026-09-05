"""A blocked channel stops appearing everywhere a NAME search can land (V2-596).

The operator's ask, verbatim in spirit: «I tell him that I do not want to see channels made with artificial
intelligence. As he discovers which channels they are, he will remove them». The FILTER lives in the widget's
data (blocked_channels + block/unblock actions); the KNOWLEDGE of which channels match a criterion lives with
the brain, which names them one by one. Three doors run name searches — load-by-query, add-by-query and
`search` — and all three must honor the filter, while an EXPLICIT pasted link is an order and is never
filtered: blocking must not make the player disobey a URL the operator chose himself.
"""
import io
import urllib.request

import pytest

from widgets.youtube import data as yt
from widgets import store

# First hit from the channel the operator refuses; the second is fine. Ids are 11 chars, page order matters.
_HTML = (
    '{"videoRenderer":{"videoId":"AAAAAAAAAA1",'
    '"title":{"runs":[{"text":"Top 10 coches del futuro"}]},'
    '"ownerText":{"runs":[{"text":"Lucid AI Cars"}]}}}'
    '{"videoRenderer":{"videoId":"BBBBBBBBBB2",'
    '"title":{"runs":[{"text":"Prueba real del Ferrari F40"}]},'
    '"ownerText":{"runs":[{"text":"Motor Clasico"}]}}}'
)


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=6: io.BytesIO(_HTML.encode("utf-8")))


def test_block_channel_stores_it_and_sweeps_the_list_but_not_playback(sandbox):
    yt.apply_action("add", {"url": "https://youtu.be/AAAAAAAAAA1", "title": "Coches IA"})
    db = yt._load(); db["list"][0]["channel"] = "Lucid AI Cars"; store.save(yt.WID, db)
    yt.apply_action("add", {"url": "https://youtu.be/BBBBBBBBBB2", "title": "Ferrari"})
    yt.apply_action("load", {"url": "https://youtu.be/CCCCCCCCCC3", "title": "Sonando"})
    r = yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    assert r["ok"] and r["removed_from_list"] == 1 and "Lucid AI Cars" in r["blocked"]
    d = yt.view_data()
    assert [it["title"] for it in d["list"]] == ["Ferrari"]
    assert d["videoId"] == "CCCCCCCCCC3" and d["paused"] is False   # only `close` stops playback (V2-366)


def test_search_drops_blocked_channels_and_says_how_many(sandbox):
    yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    r = yt.apply_action("search", {"query": "coches"})
    assert r["ok"] and r["blocked_out"] == 1
    assert [it["channel"] for it in yt.view_data()["list"]] == ["Motor Clasico"]


def test_all_results_blocked_is_said_honestly_not_as_a_worse_search(sandbox):
    yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    yt.apply_action("block_channel", {"channel": "Motor Clasico"})
    r = yt.apply_action("search", {"query": "coches"})
    assert r["ok"] is False and r["error"] == "all_blocked" and r["blocked_out"] == 2
    assert "bloqueados" in r["message"]


def test_load_by_name_skips_a_blocked_top_hit(sandbox):
    yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    r = yt.apply_action("load", {"query": "coches del futuro"})
    assert r["ok"] and yt.view_data()["videoId"] == "BBBBBBBBBB2"


def test_an_explicit_link_is_an_order_and_is_never_filtered(sandbox):
    yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    r = yt.apply_action("load", {"url": "https://youtu.be/AAAAAAAAAA1", "title": "Lo pedi yo"})
    assert r["ok"] and yt.view_data()["videoId"] == "AAAAAAAAAA1"


def test_a_short_blocked_term_matches_whole_name_only(sandbox):
    # «ia» blocked as a NAME must not wipe every channel containing those two letters by substring.
    assert yt._is_blocked("Diario de un viaje", ["ia"]) is False
    assert yt._is_blocked("ia", ["ia"]) is True
    assert yt._is_blocked("Lucid AI Cars espanol", ["lucid ai cars"]) is True   # 4+ chars: containment


def test_unblock_restores_discoverability(sandbox):
    yt.apply_action("block_channel", {"channel": "Lucid AI Cars"})
    r = yt.apply_action("unblock_channel", {"channel": "lucid"})
    assert r["ok"] and r["channel"] == "Lucid AI Cars" and r["blocked"] == []
    r2 = yt.apply_action("search", {"query": "coches"})
    assert r2["ok"] and "blocked_out" not in r2


def test_blocking_nothing_teaches_the_retry(sandbox):
    r = yt.apply_action("block_channel", {})
    assert r["ok"] is False and "canal" in r["message"]
    r2 = yt.apply_action("unblock_channel", {"channel": "nadie"})
    assert r2["ok"] is False and r2["error"] == "not_blocked"
