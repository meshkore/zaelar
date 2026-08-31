"""V2-294 — a half-loaded page returns HOLLOW rows, and that is not “no results”.

Measured in the 2026-08-24 13:57 batch, `search-secondhand-monitor__es`. Three seconds after navigating to the
listing with the filter already applied, extraction returned:

    [ { "title": "", "price": "0 €", "tel": "", "url": "https://es.wallapop.com/item/monitor-1043173153", … } … ]

These are the SKELETON cards that a listing renders while hydrating: the link is already there, the rest blank. The
worker diagnosed it on its own —“extraction returns poor data (empty titles, prices at 0)”— and spent two
rounds recovering; the next extraction, **on the same page**, returned real monitors with prices. In
`search-buy-bicycle__es` and `search-buy-guitar__es` the round ended before it recovered: `extr=0` for three
consecutive batches.

The signal to look again is unambiguous and does not need to know which site it is: **there are rows and NONE has
an identity**. With ZERO rows, there is no retry —that can indeed be a page with no results, and making every empty
search wait two seconds would make all of them pay to fix a few— and only ONCE, because on the second attempt it is
no longer merely loading.
"""
import asyncio

import pytest

from widgets.navegador import act_api

_HUECAS = [{"title": "", "price": "0 €", "url": "https://es.wallapop.com/item/monitor-1043173153"},
           {"title": "", "price": "0 €", "url": "https://es.wallapop.com/item/monitor-1043173154"}]
_REALES = [{"title": "Monitor MSI MAG 276CXF 27 LED Curvo 280Hz", "price": "100 €", "url": "https://x/1"},
           {"title": "Dell UltraSharp U2414H Monitor", "price": "115 €", "url": "https://x/2"}]


class _Tab:
    """A tab that returns a different list on each extraction, as one that is hydrating does."""
    def __init__(self, *rondas):
        self.rondas, self.n = list(rondas), 0

    async def ensure(self):
        return None

    async def extract_listings(self, limit):
        out = self.rondas[min(self.n, len(self.rondas) - 1)]
        self.n += 1
        return out

    #: V2-323 added a SECOND look, for pages that render as you approach, and it needs the real page.
    #: It is deliberately declared OFF here: these tests measure the V2-294 look (hydration), and only that.
    #: Leaving the attribute out would not have meant “not participating” — it would have been an `AttributeError`
    #: converted into an error response, which is how we discovered that the tab contract had grown.
    page = None


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """No real waiting (the test does not measure seconds) and no touching the sheet, bus, or conversation."""
    monkeypatch.setattr(act_api, "_HYDRATE_WAIT_S", 0)
    monkeypatch.setattr(act_api, "_emit_nav", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_say_phase", lambda *a, **k: None)
    monkeypatch.setattr(act_api, "_hand_over", lambda *a, **k: None)
    # The V2-323 nudge is turned off here: with a fake page there is nothing to traverse, and these tests measure
    # the HYDRATION look. Turning it off explicitly is what keeps each test measuring ONE thing.
    async def _sin_empujon(_page):
        return False
    monkeypatch.setattr(act_api._lazy, "materialise_below_the_fold", _sin_empujon)
    yield


def _run(tab, monkeypatch):
    """Through the REAL bridge path (`navegador_act`), not by calling the predicate directly: the lesson from V2-199 is
    that a test that does not traverse the path only proves that the code compiles. ONLY the tab registry is replaced,
    as it is the boundary with Chromium."""
    from widgets.navegador import owner
    monkeypatch.setitem(owner._task_browsers, "t1", tab)
    return asyncio.run(act_api.navegador_act(task_id="t1", action="extract", args={"limit": 14}))


# ── the predicate, where the decision lives ────────────────────────────────────────────────────────────────
def test_hollow_rows_have_no_identity():
    """The signal: rows with a link and nothing else. `by_identity` already knows how to answer it — no new criterion is needed."""
    named, unnamed = act_api.by_identity(_HUECAS)
    assert named == [] and len(unnamed) == 2


def test_real_rows_do_have_identity():
    assert len(act_api.by_identity(_REALES)[0]) == 2


# ── and the RETRY, through the real bridge path ───────────────────────────────────────────────────────────
def test_a_hollow_page_is_looked_at_once_more(monkeypatch):
    """THE MEASURED CASE: first extraction hollow, second with real monitors."""
    tab = _Tab(_HUECAS, _REALES)
    out = _run(tab, monkeypatch)
    assert tab.n == 2, "no volvió a mirar"
    assert [i["title"] for i in out["listings"]] == [i["title"] for i in _REALES]


def test_a_page_that_is_really_empty_is_not_retried(monkeypatch):
    """Zero rows CAN be a page with no results. Retrying there makes every empty search wait."""
    tab = _Tab([], [])
    out = _run(tab, monkeypatch)
    assert tab.n == 1
    assert out["n"] == 0


def test_a_good_page_is_not_looked_at_twice(monkeypatch):
    """Without this, “look again” is satisfied by always looking twice, which doubles the cost of every extraction."""
    tab = _Tab(_REALES, _REALES)
    out = _run(tab, monkeypatch)
    assert tab.n == 1
    assert out["n"] == 2


def test_it_gives_up_after_one_more_look(monkeypatch):
    """A page that remains hollow is not loading: what is there is delivered and the worker decides (change the search
or the site). Persisting here is the loop that V2-186 was introduced to cut."""
    tab = _Tab(_HUECAS, _HUECAS, _REALES)
    out = _run(tab, monkeypatch)
    assert tab.n == 2
    assert [i["title"] for i in out["listings"]] == ["", ""]


def test_the_retry_result_is_only_kept_when_it_is_better(monkeypatch):
    """If the second look brings LESS, keeping it would make things worse because of retrying."""
    tab = _Tab(_HUECAS, [])
    out = _run(tab, monkeypatch)
    assert out["n"] == 2, "se quedó con la segunda, que traía menos que la primera"
