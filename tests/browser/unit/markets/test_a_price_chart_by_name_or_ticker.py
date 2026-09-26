"""The markets widget (demo run, 2026-09-26): «Show me a chart of Apple stock today» used to get «I can't actually
display a chart here». What is measured: a NAME resolves to a ticker, the move is against yesterday's close for
«today» and against the period's start otherwise, the operator's period words map onto a range, a 429 retries on
the twin host, and `view_data` never touches the network."""
import json
import urllib.error

import pytest

from widgets.markets import data as mk


def _chart(symbol="AAPL", closes=(100.0, 102.0, 110.0), prev=105.0, price=110.0):
    return {"chart": {"result": [{
        "meta": {"symbol": symbol, "currency": "USD", "shortName": "Apple Inc.", "regularMarketPrice": price,
                 "previousClose": prev, "chartPreviousClose": prev, "regularMarketTime": 1790366400,
                 "fullExchangeName": "NasdaqGS"},
        "timestamp": [1790300000 + i * 300 for i in range(len(closes))],
        "indicators": {"quote": [{"close": list(closes)}]}}]}}


@pytest.fixture
def fake_yahoo(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))
    calls = []

    def get(url):
        calls.append(url)
        if "/search?" in url:
            return {"quotes": [{"symbol": "AAPL", "shortname": "Apple Inc.", "quoteType": "EQUITY"}]}
        return _chart()
    monkeypatch.setattr(mk, "_get", get)
    monkeypatch.setattr(mk.store, "load", lambda wid, seed, **k: json.loads(json.dumps(_mem.get(wid, seed))))
    monkeypatch.setattr(mk.store, "save", lambda wid, db: _mem.__setitem__(wid, json.loads(json.dumps(db))))
    _mem.clear()
    return calls


_mem: dict = {}


def test_a_name_is_looked_up_and_today_moves_against_yesterdays_close(fake_yahoo):
    got = mk.apply_action("show", {"symbol": "Apple", "range": "today"})
    assert got["ok"] and got["symbol"] == "AAPL" and got["range"] == "1d", got
    assert got["change_pct"] == round((110 - 105) / 105 * 100, 2), "«today» is against the previous close"
    assert any("/search?" in u for u in fake_yahoo), "a name must be looked up, not sent as a ticker"
    assert "Apple Inc. (AAPL) 110.00 USD, up" in got["summary"]


def test_a_ticker_is_taken_as_it_is(fake_yahoo):
    mk.apply_action("show", {"symbol": "AAPL"})
    assert not any("/search?" in u for u in fake_yahoo)


def test_the_last_month_instead_moves_against_the_start_of_the_period(fake_yahoo):
    mk.apply_action("show", {"symbol": "AAPL"})
    got = mk.apply_action("range", {"range": "the last month instead"})
    assert got["range"] == "1mo"
    assert got["change_pct"] == round((110 - 100) / 100 * 100, 2), "a period moves against where it started"
    assert "range=1mo" in fake_yahoo[-1]


@pytest.mark.parametrize("said,want", [("today", "1d"), ("this week", "5d"), ("last month", "1mo"),
                                       ("el último mes", "1mo"), ("six months", "6mo"), ("this year", "1y"),
                                       ("the whole year", "1y"), ("5 years", "5y"), ("1mo", "1mo"), ("", "1d")])
def test_the_period_words_map_onto_a_range(said, want):
    assert mk._range_of(said) == want


def test_range_without_a_chart_teaches_the_first_step(fake_yahoo):
    got = mk.apply_action("range", {"range": "1y"})
    assert not got["ok"] and "'show'" in got["error"]


def test_a_429_is_retried_once_on_the_twin_host(monkeypatch):
    seen = []

    class _R:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b'{"ok": 1}'

    def urlopen(req, timeout=0):
        seen.append(req.full_url)
        if "//query1." in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, None)
        return _R()
    monkeypatch.setattr(mk.urllib.request, "urlopen", urlopen)
    assert mk._get("https://query1.finance.yahoo.com/v8/finance/chart/AAPL") == {"ok": 1}
    assert [u.split("//")[1][:6] for u in seen] == ["query1", "query2"]


def test_view_data_never_touches_the_network(monkeypatch, tmp_path):
    monkeypatch.setenv("ZAELAR_WORKSPACE", str(tmp_path))

    def boom(*a, **k):
        raise AssertionError("view_data reached the network — it is the hot path, it serves the cache")
    monkeypatch.setattr(mk.urllib.request, "urlopen", boom)
    v = mk.view_data()
    assert v["ranges"] == ["1d", "5d", "1mo", "6mo", "1y", "5y"] and v["symbol"] == ""


def test_the_widget_is_shipped_and_declares_exactly_what_it_handles():
    from widgets import registry
    assert registry.origin_of({"id": "markets"}) == "builtin"
    man = json.load(open(mk.__file__.replace("data.py", "manifest.json")))
    assert set(man["actions"]) == {"show", "range", "refresh"}
    for a in man["actions"]:
        assert "unknown action" not in str(mk.apply_action(a, {}).get("error", "")), a
