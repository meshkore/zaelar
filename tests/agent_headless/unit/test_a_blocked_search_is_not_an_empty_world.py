"""Being BLOCKED and the world containing nothing are opposite facts, yet they arrived identical.

Measured live on 2026-08-27, using the queries run by the US cases: 4 of 6 came back empty because
DuckDuckGo was serving an anti-bot challenge. Nothing in the system said so. Three layers failed at once,
and each one silently:

  1. the block arrives as **HTTP 202**, which is a SUCCESS status: `raise_for_status()` lets it through, the
     link regex finds nothing, and the caller receives `results: []`.
  2. the classifier looked for the words WE would use to describe it («captcha», «unusual
     traffic»). The real page says «Unfortunately, bots use DuckDuckGo too… Select all squares containing a
     duck», and the word «captcha» appears nowhere, so a hard block was classified as «error».
  3. the search observability row carried `n: 0` and the query, but NOT A SINGLE word about why — so
     `search_health`, which exists precisely to catch this confusion, scraped prose that did not exist and
     declared a dead search layer healthy.

`browser_search._looks_blocked` already did this for Google. The DDG step—the last in the chain, the one that
runs when there is neither a key nor a browser—had nothing.
"""
from __future__ import annotations

import json

from nucleo import websearch as W
from tests.use_cases.e2e.agent import verify as V

_REAL_PAGE = ("<html><body><!--> DuckDuckGo Unfortunately, bots use DuckDuckGo too. Please complete the "
              "following challenge to confirm this search was made by a human. Select all squares containing "
              "a duck: Submit </body></html>")


def test_the_real_block_page_is_recognised():
    """The REAL page, copied from a live response—not one that says «captcha» for our convenience."""
    assert W._challenge_reason(_REAL_PAGE)
    assert "captcha" in W._challenge_reason(_REAL_PAGE)


def test_a_page_of_results_is_not_a_block():
    """The sensitivity half: without this, «reads blocks» and «calls everything a block» pass alike."""
    assert W._challenge_reason("<html><a href='http://x.es'>Hoteles baratos en Austin</a></html>") == ""
    assert W._challenge_reason("") == ""


def test_the_classifier_knows_the_words_the_page_actually_uses():
    """Before, this was «error», which is the same as saying nothing."""
    assert W._classify_failure("ddg: captcha: DuckDuckGo sirvió un desafío («made by a human»)") == "captcha"
    assert W._classify_failure("bots use duckduckgo too") == "captcha"
    assert W._classify_failure("ddg: sin resultados") == "error", "no todo vacío es un bloqueo"


def test_the_reason_travels_with_the_result(monkeypatch):
    """`note_failure` turns on the operator's signal; the row needs the reason UP FRONT."""
    monkeypatch.setattr(W, "_order", lambda: ["ddg"])
    monkeypatch.setitem(W._BACKENDS, "ddg", lambda q, k: (_ for _ in ()).throw(RuntimeError(
        "captcha: DuckDuckGo sirvió un desafío anti-bot («made by a human»)")))
    res = W.search("buy used bicycle", 5)
    assert res["results"] == []
    assert res["failure"]["kind"] == "captcha"
    assert "desafío" in res["failure"]["detail"]


def test_an_honest_empty_world_still_says_so(monkeypatch):
    """A search engine that responds and finds nothing MUST NOT come out as a block."""
    monkeypatch.setattr(W, "_order", lambda: ["ddg"])
    monkeypatch.setitem(W._BACKENDS, "ddg", lambda q, k: {"query": q, "answer": "", "results": [],
                                                          "source": "ddg", "ai": False})
    res = W.search("xyzzy nada de nada", 5)
    assert res["failure"]["kind"] == "error", "sin señal de bloqueo, no se inventa una"


def _row(**extra) -> dict:
    """The search row exactly as returned by `/api/observability/events`."""
    return {"kind": "search", "cat": "flash",
            "payload": json.dumps({"kind": "search", "label": "🔎 resultados web",
                                   "text": "cheap hotels austin", "n": 0, **extra})}


def test_the_harness_reads_the_field_not_the_prose():
    """Measured against the real SHAPE of the data: a field, not a sentence someone had to write."""
    sano = V.search_health([_row(n=6)])
    assert sano["degraded"] is False and sano["reasons"] == []
    roto = V.search_health([_row(failure={"kind": "captcha", "detail": "desafío anti-bot"})])
    assert roto["degraded"] is True and roto["reasons"] == [("blocked", 1)]


def test_the_old_prose_route_still_works():
    """The worker's own WebSearch does write its reason in words; that path must not break."""
    prosa = V.search_health([{"kind": "search", "text": "Weekly/Monthly Limit Exhausted", "label": ""}])
    assert prosa["degraded"] is True and prosa["reasons"] == [("quota_exhausted", 1)]


def test_a_quota_failure_is_not_reported_as_a_block():
    """The two reasons lead to different actions: one is expected, the other is worked around."""
    got = V.search_health([_row(failure={"kind": "quota", "detail": "limit exhausted"})])
    assert got["reasons"] == [("quota_exhausted", 1)]


class _FakeResp:
    def __init__(self, text: str, status: int = 202):
        self.text, self.status_code = text, status

    def raise_for_status(self):
        """202 is a SUCCESS status: this does NOT raise, which is why the block went unnoticed."""
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return {}


class _FakeClient:
    def __init__(self, page: str):
        self._page = page

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, *a, **kw):
        return _FakeResp(self._page)

    def get(self, *a, **kw):
        return _FakeResp("{}", 200)      # the instant answer, neutralized


def test_the_ddg_backend_itself_raises_on_the_202_challenge(monkeypatch):
    """THE PLUMBING, not a mocked version of it.

Without this test, the entire `_ddg` recognition can be removed and the others still stay green: they all
inject the failure from above. Measured when dismantling it on 2026-08-27—8 green tests for the restored defect.
    """
    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeClient(_REAL_PAGE))
    try:
        W._ddg("buy used bicycle", 5)
    except RuntimeError as e:
        assert "captcha" in str(e)
    else:
        raise AssertionError("un desafío servido como 202 tiene que LEVANTAR, no volver vacío")


def test_and_a_normal_200_with_no_matches_does_not_raise(monkeypatch):
    """The other half: a legitimate results page that simply contains nothing is NOT a block."""
    import httpx
    monkeypatch.setattr(httpx, "Client", _FakeClient("<html><body>No results found.</body></html>"))
    assert W._ddg("xyzzy", 5)["results"] == []
