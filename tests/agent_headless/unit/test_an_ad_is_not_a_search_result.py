"""V2-469 · a search-engine AD is not a search result.

Measured in `cheapest-monitor__us` (23:43): the sheet's first two «candidates» were DuckDuckGo ad
redirects (`duckduckgo.com/y.js?ad_domain=idealo.es&ad_provider=bingv7aa&ad_type=txad`) with SPANISH
titles on the US engine — ads follow the machine's IP, not the engine's locale, so they poison every
consumer downstream (brain notes, worker leads, the results sheet) with wrong-market rows that read like
findings. `_ddg_href` already unwraps ORGANIC redirects; the ad rows passed through whole. An ad row is
recognized by its URL alone and skipped at the SOURCE, so no consumer ever sees it.
"""
from nucleo import websearch as W

_AD = ("https://duckduckgo.com/y.js?ad_domain=idealo.es&ad_provider=bingv7aa&ad_type=txad"
       "&click_metadata=abc&u3=https%3A%2F%2Fwww.bing.com")


def test_the_measured_ad_url_is_recognized():
    assert W._is_ad(_AD)


def test_organic_urls_are_not_ads():
    assert not W._is_ad("https://bestoftbest.com/computer-peripherals/best-budget-27-inch-monitors-2026/")
    assert not W._is_ad("https://www.rtings.com/monitor/reviews/best/budget")


def test_assembly_skips_ads_and_fills_the_quota_with_organic_rows():
    links = [(_AD, "Monitores 4K al mejor precio"),
             ("https://a.example/one", "Real review one"),
             ("https://b.example/two", "Real review two")]
    snippets = ["ad snippet", "real one", "real two"]
    rows = W._assemble_ddg_results(links, snippets, 2)
    assert [r["url"] for r in rows] == ["https://a.example/one", "https://b.example/two"]


def test_a_page_that_mentions_ads_in_its_path_is_not_an_ad():
    """The cut is the redirect's shape (host + y.js / ad params), never the word."""
    assert not W._is_ad("https://example.com/blog/why-ads-are-bad")
