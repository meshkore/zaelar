"""V2-469 · a hit the parser cannot NAME is not a candidate — Shorts blocks carry no title.

Measured in `find-videos-on-a-topic-no-ai-slop` (2026-08-28 22:31, deterministically reproducible): the
results page for the round's query led with SHORTS — blocks that repeat `"videoId"` but carry
`reelPlayerOverlayRenderer` instead of `"title":{"runs":…}` — so `_search_many` returned 5 hits, ALL
with empty title and channel. Downstream every one became a bare «youtu.be/<id>» row, the canned line
announced «Te he puesto 5 vídeos: “youtu.be/T41j…”» and the user answered, reasonably: «no me has
puesto ningún título. Así me es imposible elegir».

A search exists so the operator can CHOOSE, and choosing needs a name: an untitled hit is skipped and
the parser keeps walking the page until it has n NAMED ones. A page with no nameable hit returns [] —
the `search` action already says «No encontré vídeos de eso» for that, which is honest; five unnameable
rows are not.
"""
import io
import urllib.request

import pytest

from widgets.youtube import data as yt
from widgets import store

# The real page's shape, condensed: two Shorts blocks first (videoId, reel overlay, NO title), then
# ordinary videoRenderer blocks with names.
_HTML = (
    '{"videoId":"SHORTAAAAA1","thumbnail":{"thumbnails":[{"url":"x","width":1080,"height":1920}]},'
    '"overlay":{"reelPlayerOverlayRenderer":{"style":"REEL_PLAYER_OVERLAY_STYLE_SHORTS"}}}'
    '{"videoId":"SHORTBBBBB2","overlay":{"reelPlayerOverlayRenderer":{}}}'
    '{"videoRenderer":{"videoId":"GOODAAAAAA1",'
    '"title":{"runs":[{"text":"Poda del olivo paso a paso"}]},'
    '"ownerText":{"runs":[{"text":"El Olivar de Justo"}]}}}'
    '{"videoRenderer":{"videoId":"GOODBBBBBB2",'
    '"title":{"runs":[{"text":"Curso completo para podar un olivo"}]}}}'
)

_ONLY_SHORTS = (
    '{"videoId":"SHORTAAAAA1","overlay":{"reelPlayerOverlayRenderer":{}}}'
    '{"videoId":"SHORTBBBBB2","overlay":{"reelPlayerOverlayRenderer":{}}}'
)


@pytest.fixture
def page(monkeypatch, tmp_path):
    monkeypatch.setattr(store, "DATA_DIR", str(tmp_path))

    def _serve(html):
        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda req, timeout=6: io.BytesIO(html.encode("utf-8")))
    return _serve


def test_untitled_shorts_are_skipped_and_named_hits_fill_the_quota(page):
    page(_HTML)
    hits = yt._search_many("como podar un olivo", 5)
    assert [h["videoId"] for h in hits] == ["GOODAAAAAA1", "GOODBBBBBB2"]
    assert all(h["title"] for h in hits)


def test_a_page_with_no_nameable_hit_returns_empty_not_bare_ids(page):
    page(_ONLY_SHORTS)
    assert yt._search_many("como podar un olivo", 5) == []


def test_n_counts_named_hits_not_page_blocks(page):
    page(_HTML)
    assert [h["videoId"] for h in yt._search_many("olivo", 1)] == ["GOODAAAAAA1"]
